import uuid

import pytest
from flask import json
from jsonschema.exceptions import ValidationError

from app.dao.api_key_dao import save_model_api_key
from app.models import ApiKey, KEY_TYPE_NORMAL, EMAIL_TYPE, SMS_TYPE, TEMPLATE_TYPES
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
    "inbound_sms_list": [valid_inbound_sms]
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
    "inbound_sms_list": [invalid_inbound_sms]
}


def _get_inbound_sms(client, inbound_sms, url):
    auth_header = create_authorization_header(service_id=inbound_sms.service_id)
    response = client.get(url, headers=[auth_header])
    return json.loads(response.get_data(as_text=True))


def test_get_inbound_sms_contract(client, sample_inbound_sms):
    response_json = _get_inbound_sms(
        client,
        sample_inbound_sms,
        '/v2/inbound_sms/{}'.format(sample_inbound_sms.user_number)
    )
    res = validate(response_json, get_inbound_sms_response)


def test_valid_inbound_sms_json():
    validate(valid_inbound_sms, get_inbound_sms_single_response)


def test_valid_inbound_sms_list_json():
    validate(valid_inbound_sms_list, get_inbound_sms_response)


def test_invalid_inbound_sms_json():
    with pytest.raises(expected_exception=ValidationError):
        validate(invalid_inbound_sms, get_inbound_sms_single_response)


def test_invalid_inbound_sms_list_json():
    with pytest.raises(expected_exception=ValidationError):
        validate(invalid_inbound_sms_list, get_inbound_sms_response)
