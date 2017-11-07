import pytest
from flask import json
from jsonschema.exceptions import ValidationError

from app.v2.inbound_sms.inbound_sms_schemas import get_inbound_sms_response, get_inbound_sms_single_response
from app.schema_validation import validate

from tests import create_authorization_header


valid_inbound_sms = {
    "provider_date": "2017-11-02T15:07:57.199541Z",
    "provider_reference": "foo",
    "user_number": "447700900111",
    "created_at": "2017-11-02T15:07:57.197546Z",
    "service_id": "a5149c32-f03b-4711-af49-ad6993797d45",
    "id": "342786aa-23ce-4695-9aad-7f79e68ee29a",
    "notify_number": "testing",
    "content": "Hello"
}

valid_inbound_sms_list = {
    "received_text_messages": [valid_inbound_sms],
    "links": {
        "current": valid_inbound_sms["id"]
    }

}

invalid_inbound_sms = {
    "provider_date": "2017-11-02T15:07:57.199541",
    "provider_reference": "foo",
    "user_number": "447700900111",
    "created_at": "2017-11-02T15:07:57.197546",
    "service_id": "a5149c32-f03b-4711-af49-ad6993797d45",
    "id": "342786aa-23ce-4695-9aad-7f79e68ee29a",
    "notify_number": "testing"
}

invalid_inbound_sms_list = {
    "received_text_messages": [invalid_inbound_sms]
}


def test_get_inbound_sms_contract(client, sample_inbound_sms):
    auth_header = create_authorization_header(service_id=sample_inbound_sms.service_id)
    response = client.get('/v2/received-text-messages/{}'.format(sample_inbound_sms.user_number), headers=[auth_header])
    response_json = json.loads(response.get_data(as_text=True))

    assert validate(response_json, get_inbound_sms_response)['received_text_messages'][0] \
        == sample_inbound_sms.serialize()


def test_valid_inbound_sms_json():
    assert validate(valid_inbound_sms, get_inbound_sms_single_response) == valid_inbound_sms


def test_valid_inbound_sms_list_json():
    validate(valid_inbound_sms_list, get_inbound_sms_response)


def test_invalid_inbound_sms_json():
    with pytest.raises(expected_exception=ValidationError):
        validate(invalid_inbound_sms, get_inbound_sms_single_response)


def test_invalid_inbound_sms_list_json():
    with pytest.raises(expected_exception=ValidationError):
        validate(invalid_inbound_sms_list, get_inbound_sms_response)
