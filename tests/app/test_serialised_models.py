import json
from unittest.mock import ANY, call

import pytest
from freezegun import freeze_time

from app.serialised_models import SerialisedTemplate, memory_cache
from tests.app.db import create_template

EXPECTED_TEMPLATE_ATTRIBUTES = {
    "archived",
    "coerce_value_to_type",
    "content",
    "from_id_and_service_id",
    "from_id_service_id_and_version",
    "get_dict",
    "has_unsubscribe_link",
    "id",
    "postage",
    "reply_to_text",
    "subject",
    "template_type",
    "version",
}


@freeze_time("2025-08-06 01:02:03")
def test_template_caches_in_redis_with_correct_keys(
    admin_request,
    sample_service,
    mocker,
):
    mock_redis_set = mocker.patch("app.serialised_models.redis_cache.redis_client.set")

    sample_template = create_template(service=sample_service)

    template = SerialisedTemplate.from_id_and_service_id(sample_template.id, sample_service.id)

    mock_redis_set.assert_called_once_with(
        f"service-{sample_service.id}-template-{sample_template.id}-version-None",
        ANY,
        ex=2419200,
    )

    assert json.loads(mock_redis_set.call_args_list[0][0][1]) == {
        "data": {
            "archived": False,
            "content": "Dear Sir/Madam, Hello. Yours Truly, The Government.",
            "created_at": "2025-08-06T01:02:03.000000Z",
            "created_by": str(sample_template.created_by.id),
            "folder": None,
            "has_unsubscribe_link": False,
            "hidden": False,
            "id": str(sample_template.id),
            "is_precompiled_letter": False,
            "letter_attachment": None,
            "letter_languages": None,
            "letter_welsh_content": None,
            "letter_welsh_subject": None,
            "name": "sms Template Name",
            "postage": None,
            "redact_personalisation": False,
            "reply_to_text": "testing",
            "reply_to": None,
            "service_letter_contact": None,
            "service": str(sample_service.id),
            "subject": None,
            "template_redacted": ANY,
            "template_type": "sms",
            "updated_at": None,
            "version": 1,
        }
    }

    assert {attr for attr in dir(template) if not attr.startswith("_")} == EXPECTED_TEMPLATE_ATTRIBUTES


@freeze_time("2025-08-06 01:02:03")
def test_template_version_caches_in_redis_with_correct_keys(
    admin_request,
    sample_service,
    mocker,
):
    mock_redis_set = mocker.patch("app.serialised_models.redis_cache.redis_client.set")

    sample_template = create_template(service=sample_service)

    template = SerialisedTemplate.from_id_service_id_and_version(sample_template.id, sample_service.id, version=1)

    mock_redis_set.assert_called_once_with(
        f"service-{sample_service.id}-template-{sample_template.id}-version-1",
        ANY,
        ex=2419200,
    )

    assert json.loads(mock_redis_set.call_args_list[0][0][1]) == {
        "data": {
            "archived": False,
            "content": "Dear Sir/Madam, Hello. Yours Truly, The Government.",
            "created_at": "2025-08-06T01:02:03.000000Z",
            "created_by": {
                "id": str(sample_template.created_by.id),
                "email_address": "notify@digital.cabinet-office.gov.uk",
                "name": "Test User",
            },
            "has_unsubscribe_link": False,
            "hidden": False,
            "id": str(sample_template.id),
            "is_precompiled_letter": False,
            "letter_attachment": None,
            "letter_languages": None,
            "letter_welsh_content": None,
            "letter_welsh_subject": None,
            "name": "sms Template Name",
            "postage": None,
            "reply_to_text": "testing",
            "reply_to": None,
            "service_letter_contact": None,
            "service": str(sample_service.id),
            "subject": None,
            "template_redacted": ANY,
            "template_type": "sms",
            "updated_at": None,
            "version": 1,
        }
    }

    assert {attr for attr in dir(template) if not attr.startswith("_")} == EXPECTED_TEMPLATE_ATTRIBUTES


def test_memory_cache_caches(mocker):
    expensive = mocker.Mock()

    class Model:
        @classmethod
        @memory_cache
        def cached_with_default_args(cls, *args, **kwargs):
            expensive(*args, **kwargs)

        @classmethod
        @memory_cache(ttl=3)
        def cached_with_custom_ttl(cls, *args, **kwargs):
            expensive(*args, **kwargs)

    for _ in range(10):
        Model.cached_with_default_args("foo", a=1)
        Model.cached_with_custom_ttl("bar", b=2)
        Model.cached_with_custom_ttl("bar", c=3)

    assert expensive.call_args_list == [call("foo", a=1), call("bar", b=2), call("bar", c=3)]


def test_memory_cache_not_shared_between_classes(mocker):
    expensive = mocker.Mock()

    class Model_A:
        @classmethod
        @memory_cache
        def foo(cls):
            expensive("from Model_A")

    class Model_B:
        @classmethod
        @memory_cache
        def foo(cls):
            expensive("from Model_B")

    Model_A.foo()
    Model_B.foo()

    assert expensive.call_args_list == [call("from Model_A"), call("from Model_B")]


def test_results_of_memory_cache(mocker):
    class Model:
        @classmethod
        @memory_cache
        def a(cls):
            return "a"

        @classmethod
        @memory_cache
        def b(cls):
            return "b"

    assert [Model.a() for _ in range(3)] == ["a", "a", "a"]
    assert [Model.b() for _ in range(3)] == ["b", "b", "b"]


def test_memory_cache_on_plain_function(mocker):
    @memory_cache
    def not_a_classmethod(*args):
        pass

    with pytest.raises(TypeError):
        not_a_classmethod()

    with pytest.raises(TypeError):
        not_a_classmethod("foo")


def test_memory_cache_on_non_class_method(mocker):
    class Model:
        @memory_cache
        def not_a_classmethod(self, *args):
            pass

    with pytest.raises(TypeError):
        Model().not_a_classmethod()

    with pytest.raises(TypeError):
        Model().not_a_classmethod("foo")
