from collections import defaultdict
from functools import partial
from threading import RLock

import cachetools
from notifications_utils.clients.redis import RequestCache
from notifications_utils.serialised_model import (
    SerialisedModel,
    SerialisedModelCollection,
)
from werkzeug.utils import cached_property

from app import db, redis_store

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
    @redis_cache.set('service-{service_id}-template-{template_id}-version-None')
    def get_dict(template_id, service_id):
        from app.dao import templates_dao
        from app.schemas import template_schema

        fetched_template = templates_dao.dao_get_template_by_id_and_service_id(
            template_id=template_id,
            service_id=service_id
        )

        template_dict = template_schema.dump(fetched_template).data
        db.session.commit()

        return {'data': template_dict}


class SerialisedService(SerialisedModel):
    ALLOWED_PROPERTIES = {
        'id',
        'active',
        'contact_link',
        'email_from',
        'message_limit',
        'permissions',
        'rate_limit',
        'research_mode',
        'restricted',
    }

    @classmethod
    @memory_cache
    def from_id(cls, service_id):
        return cls(cls.get_dict(service_id)['data'])

    @staticmethod
    @redis_cache.set('service-{service_id}')
    def get_dict(service_id):
        from app.schemas import service_schema

        service_dict = service_schema.dump(dao_fetch_service_by_id(service_id)).data
        db.session.commit()

        return {'data': service_dict}

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
    @memory_cache
    def from_service_id(cls, service_id):
        keys = [
            {k: getattr(key, k) for k in SerialisedAPIKey.ALLOWED_PROPERTIES}
            for key in get_model_api_keys(service_id)
        ]
        db.session.commit()
        return cls(keys)


class SerialisedServiceCallbackApi(SerialisedModel):

    @classmethod
    @memory_cache
    def from_service_id(cls, service_id):
        service_callback_api_dict = cls.get_dict(service_id)
        if service_callback_api_dict:
            return cls(cls.get_dict(service_id))
        return None

    @staticmethod
    # Don’t cache this because we probably don’t wanna put people’s
    # bearer tokens in Redis
    def get_dict(service_id):
        service_callback_api = get_service_delivery_status_callback_api_for_service(
            service_id
        )
        if service_callback_api:
            return service_callback_api.serialize()
        return None
