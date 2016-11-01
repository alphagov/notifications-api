import uuid

import pytest
from flask import json
from jsonschema import ValidationError

from app.v2.notifications.notification_schemas import post_sms_request, post_sms_response
from app.schema_validation import validate

valid_json = {"phone_number": "07515111111",
              "template_id": str(uuid.uuid4())
              }
valid_json_with_optionals = {
    "phone_number": "07515111111",
    "template_id": str(uuid.uuid4()),
    "reference": "reference from caller",
    "personalisation": {"key": "value"}
}


@pytest.mark.parametrize("input", [valid_json, valid_json_with_optionals])
def test_post_sms_schema_is_valid(input):
    validate(input, post_sms_request)


def test_post_sms_json_schema_bad_uuid_and_missing_phone_number():
    j = {"template_id": "notUUID"}
    with pytest.raises(ValidationError) as e:
        validate(j, post_sms_request)
    error = json.loads(e.value.message)
    assert "POST v2/notifications/sms" in error['message']
    assert len(error.get('fields')) == 2
    assert "'phone_number' is a required property" in error['fields']
    assert "'template_id' not a valid UUID" in error['fields']
    assert error.get('code') == '1001'
    assert error.get('link', None) is not None


def test_post_sms_schema_with_personalisation_that_is_not_a_dict():
    j = {
        "phone_number": "07515111111",
        "template_id": str(uuid.uuid4()),
        "reference": "reference from caller",
        "personalisation": "not_a_dict"
    }
    with pytest.raises(ValidationError) as e:
        validate(j, post_sms_request)
    error = json.loads(e.value.message)
    assert "POST v2/notifications/sms" in error['message']
    assert len(error.get('fields')) == 1
    assert error['fields'][0] == "'personalisation' should contain key value pairs"
    assert error.get('code') == '1001'
    assert error.get('link', None) is not None


valid_response = {
    "id": str(uuid.uuid4()),
    "content": {"body": "contents of message",
                "from_number": "46045"},
    "uri": "/v2/notifications/id",
    "template": {"id": str(uuid.uuid4()),
                 "version": 1,
                 "uri": "/v2/template/id"}
}

valid_response_with_optionals = {
    "id": str(uuid.uuid4()),
    "reference": "reference_from_service",
    "content": {"body": "contents of message",
                "from_number": "46045"},
    "uri": "/v2/notifications/id",
    "template": {"id": str(uuid.uuid4()),
                 "version": 1,
                 "uri": "/v2/template/id"}
}


@pytest.mark.parametrize('input', [valid_response])
def test_post_sms_response_schema_is_valid(input):
    validate(input, post_sms_response)


def test_post_sms_response_schema_missing_uri():
    j = valid_response
    del j["uri"]
    with pytest.raises(ValidationError) as e:
        validate(j, post_sms_response)
    assert 'uri' in e.value.message
