import json
from unittest.mock import ANY

from freezegun import freeze_time

from app.serialised_models import SerialisedTemplate
from tests.app.db import create_template

EXPECTED_TEMPLATE_ATTRIBUTES = {
    "archived",
    "coerce_value_to_type",
    "content",
    "from_id_and_service_id",
    "get_dict",
    "has_unsubscribe_link",
    "id",
    "postage",
    "process_type",
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
            "process_type": "normal",
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

    template = SerialisedTemplate.from_id_and_service_id(sample_template.id, sample_service.id, version=1)

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
            "process_type": "normal",
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
