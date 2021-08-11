import pytest
from flask import json, url_for
from jsonschema.exceptions import ValidationError

from app.schema_validation import validate
from app.v2.inbound_sms.inbound_sms_schemas import (
    get_inbound_sms_request,
    get_inbound_sms_response,
    get_inbound_sms_single_response,
)
from tests import create_service_authorization_header
from tests.app.db import create_inbound_sms

valid_inbound_sms = {
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
    "user_number": "447700900111",
    "created_at": "2017-11-02T15:07:57.197546",
    "service_id": "a5149c32-f03b-4711-af49-ad6993797d45",
    "id": "342786aa-23ce-4695-9aad-7f79e68ee29a",
    "notify_number": "testing"
}

invalid_inbound_sms_list = {
    "received_text_messages": [invalid_inbound_sms]
}


def test_get_inbound_sms_contract(client, sample_service):
    all_inbound_sms = [
        create_inbound_sms(service=sample_service, user_number='447700900113'),
        create_inbound_sms(service=sample_service, user_number='447700900112'),
        create_inbound_sms(service=sample_service, user_number='447700900111'),
    ]
    reversed_inbound_sms = sorted(all_inbound_sms, key=lambda sms: sms.created_at, reverse=True)

    auth_header = create_service_authorization_header(service_id=all_inbound_sms[0].service_id)
    response = client.get('/v2/received-text-messages', headers=[auth_header])
    response_json = json.loads(response.get_data(as_text=True))

    validated_resp = validate(response_json, get_inbound_sms_response)
    assert validated_resp['received_text_messages'] == [i.serialize() for i in reversed_inbound_sms]
    assert validated_resp['links']['current'] == url_for(
        'v2_inbound_sms.get_inbound_sms', _external=True)
    assert validated_resp['links']['next'] == url_for(
        'v2_inbound_sms.get_inbound_sms', older_than=all_inbound_sms[0].id, _external=True)


@pytest.mark.parametrize('request_args', [
    {'older_than': "6ce466d0-fd6a-11e5-82f5-e0accb9d11a6"}, {}]
)
def test_valid_inbound_sms_request_json(client, request_args):
    validate(request_args, get_inbound_sms_request)


def test_invalid_inbound_sms_request_json(client):
    with pytest.raises(expected_exception=ValidationError):
        validate({'user_number': '447700900111'}, get_inbound_sms_request)


def test_valid_inbound_sms_response_json():
    assert validate(valid_inbound_sms, get_inbound_sms_single_response) == valid_inbound_sms


def test_valid_inbound_sms_list_response_json():
    validate(valid_inbound_sms_list, get_inbound_sms_response)


def test_invalid_inbound_sms_response_json():
    with pytest.raises(expected_exception=ValidationError):
        validate(invalid_inbound_sms, get_inbound_sms_single_response)


def test_invalid_inbound_sms_list_response_json():
    with pytest.raises(expected_exception=ValidationError):
        validate(invalid_inbound_sms_list, get_inbound_sms_response)
