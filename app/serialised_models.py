from datetime import datetime
from threading import RLock
from typing import Any

import cachetools
from notifications_utils.clients.redis import RequestCache
from notifications_utils.serialised_model import (
    SerialisedModel,
    SerialisedModelCollection,
)
from werkzeug.utils import cached_property

from app import db, redis_store
from app.dao.api_key_dao import get_model_api_keys
from app.dao.provider_details_dao import get_provider_details_by_notification_type
from app.dao.services_dao import dao_fetch_service_by_id
from app.utils import is_classmethod

redis_cache = RequestCache(redis_store)


def memory_cache(*args, ttl=2):
    def make_cached(func):
        @cachetools.cached(
            cache=cachetools.TTLCache(maxsize=1024, ttl=ttl),
            lock=RLock(),
            key=ignore_first_argument_cache_key,
        )
        def wrapper(*args, **kwargs):
            if not is_classmethod(func, args[0]):
                raise TypeError("memory_cache can only be used on classmethods")
            return func(*args, **kwargs)

        return wrapper

    if args:
        # Decorator is being used without parentheses, eg @memory_cache
        return make_cached(*args)

    # Decorator is being used with keyword arguments, eg @memory_cache(ttl=123)
    return make_cached


def ignore_first_argument_cache_key(cls, *args, **kwargs):
    return cachetools.keys.hashkey(*args, **kwargs)


class SerialisedTemplate(SerialisedModel):
    archived: bool
    content: str
    id: Any
    service: Any
    postage: str
    reply_to_text: str
    subject: str
    template_type: str
    version: int
    has_unsubscribe_link: bool
    email_files: list

    @classmethod
    @memory_cache
    def from_id_and_service_id(cls, template_id, service_id):
        return cls(cls.get_dict(template_id, service_id, None)["data"])

    @classmethod
    @memory_cache(ttl=30)
    def from_id_service_id_and_version(cls, template_id, service_id, version):
        if version is None:
            raise TypeError("version must be provided for caching")
        return cls(cls.get_dict(template_id, service_id, version)["data"])

    @staticmethod
    @redis_cache.set("service-{service_id}-template-{template_id}-version-{version}")
    def get_dict(template_id, service_id, version):
        from app.dao import templates_dao
        from app.schemas import template_history_schema, template_schema

        fetched_template = templates_dao.dao_get_template_by_id_and_service_id(
            template_id=template_id,
            service_id=service_id,
            version=version,
        )

        if version:
            template_dict = template_history_schema.dump(fetched_template)
        else:
            template_dict = template_schema.dump(fetched_template)

        db.session.commit()

        return {"data": template_dict}

    @cached_property
    def email_file_objects(self):
        return SerialisedTemplateEmailFileCollection(self.email_files)


class SerialisedTemplateEmailFile(SerialisedModel):
    id: Any
    filename: str
    link_text: str
    retention_period: int
    validate_users_email: bool


class SerialisedTemplateEmailFileCollection(SerialisedModelCollection):
    model = SerialisedTemplateEmailFile


class SerialisedService(SerialisedModel):
    id: Any
    name: str
    active: bool
    contact_link: str
    custom_email_sender_name: str
    email_sender_local_part: str
    email_message_limit: int
    letter_message_limit: int
    sms_message_limit: int
    international_sms_message_limit: int
    permissions: Any
    rate_limit: int
    restricted: bool
    prefix_sms: bool
    email_branding: Any

    @classmethod
    @memory_cache
    def from_id(cls, service_id):
        return cls(cls.get_dict(service_id)["data"])

    @staticmethod
    @redis_cache.set("service-{service_id}")
    def get_dict(service_id):
        from app.schemas import service_schema

        service_dict = service_schema.dump(dao_fetch_service_by_id(service_id))
        db.session.commit()

        return {"data": service_dict}

    @cached_property
    def api_keys(self):
        return SerialisedAPIKeyCollection.from_service_id(self.id)

    def has_permission(self, permission):
        return permission in self.permissions


class SerialisedAPIKey(SerialisedModel):
    id: Any
    secret: str
    expiry_date: datetime
    key_type: str


class SerialisedAPIKeyCollection(SerialisedModelCollection):
    model = SerialisedAPIKey

    @classmethod
    @memory_cache
    def from_service_id(cls, service_id):
        keys = [
            {k: getattr(key, k) for k in SerialisedAPIKey.__annotations__} for key in get_model_api_keys(service_id)
        ]
        db.session.commit()
        return cls(keys)


class SerialisedProvider(SerialisedModel):
    identifier: str
    priority: int
    active: bool

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return False
        return self.identifier == other.identifier


class SerialisedProviders(SerialisedModelCollection):
    model = SerialisedProvider

    @classmethod
    @memory_cache(ttl=10)
    def from_notification_type(cls, notification_type, international):
        return cls(
            [
                provider.serialize()
                for provider in get_provider_details_by_notification_type(notification_type, international)
            ]
        )
