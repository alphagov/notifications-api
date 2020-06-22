from abc import ABC, abstractmethod
from collections import defaultdict
from functools import partial
from threading import RLock

import cachetools
from notifications_utils.clients.redis import RequestCache
from werkzeug.utils import cached_property

from app import redis_store

from app.dao import templates_dao
from app.dao.api_key_dao import get_model_api_keys
from app.dao.services_dao import dao_fetch_service_by_id

caches = defaultdict(partial(cachetools.TTLCache, maxsize=1024, ttl=2))
locks = defaultdict(RLock)
redis_cache = RequestCache(redis_store)


def memory_cache(func):
    @cachetools.cached(
        cache=caches[func.__qualname__],
        lock=locks[func.__qualname__],
        key=ignore_first_argument_cache_key,
    )
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    return wrapper


def ignore_first_argument_cache_key(cls, *args, **kwargs):
    return cachetools.keys.hashkey(*args, **kwargs)


class SerialisedModel(ABC):

    """
    A SerialisedModel takes a dictionary, typically created by
    serialising a database object. It then takes the value of specified
    keys from the dictionary and adds them to itself as properties, so
    that it can be interacted with like a normal database model object,
    but with no risk that it will actually go back to the database.
    """

    @property
    @abstractmethod
    def ALLOWED_PROPERTIES(self):
        pass

    def __init__(self, _dict):
        for property in self.ALLOWED_PROPERTIES:
            setattr(self, property, _dict[property])

    def __dir__(self):
        return super().__dir__() + list(sorted(self.ALLOWED_PROPERTIES))


class SerialisedModelCollection(ABC):

    """
    A SerialisedModelCollection takes a list of dictionaries, typically
    created by serialising database objects. When iterated over it
    returns a SerialisedModel instance for each of the items in the list.
    """

    @property
    @abstractmethod
    def model(self):
        pass

    def __init__(self, items):
        self.items = items

    def __bool__(self):
        return bool(self.items)

    def __getitem__(self, index):
        return self.model(self.items[index])


class SerialisedTemplate(SerialisedModel):
    ALLOWED_PROPERTIES = {
        'archived',
        'content',
        'id',
        'postage',
        'process_type',
        'reply_to_text',
        'subject',
        'template_type',
        'version',
    }

    @classmethod
    @memory_cache
    def from_id_and_service_id(cls, template_id, service_id):
        return cls(cls.get_dict(template_id, service_id)['data'])

    @staticmethod
    @redis_cache.set('template-{template_id}-version-None')
    def get_dict(template_id, service_id):
        from app.schemas import template_schema

        fetched_template = templates_dao.dao_get_template_by_id_and_service_id(
            template_id=template_id,
            service_id=service_id
        )

        template_dict = template_schema.dump(fetched_template).data

        return {'data': template_dict}


class SerialisedService(SerialisedModel):
    ALLOWED_PROPERTIES = {
        'id',
        'active',
        'contact_link',
        'email_from',
        'permissions',
        'research_mode',
        'restricted',
    }

    @classmethod
    def from_id(cls, service_id):
        return cls(cls.get_dict(service_id))

    @staticmethod
    def get_dict(service_id):
        from app.schemas import service_schema

        return service_schema.dump(dao_fetch_service_by_id(service_id)).data

    @cached_property
    def api_keys(self):
        return SerialisedAPIKeyCollection.from_service_id(self.id)


class SerialisedAPIKey(SerialisedModel):
    ALLOWED_PROPERTIES = {
        'id',
        'secret',
        'expiry_date',
        'key_type',
    }


class SerialisedAPIKeyCollection(SerialisedModelCollection):
    model = SerialisedAPIKey

    @classmethod
    def from_service_id(cls, service_id):
        return cls([
            {k: getattr(key, k) for k in SerialisedAPIKey.ALLOWED_PROPERTIES}
            for key in get_model_api_keys(service_id)
        ])
