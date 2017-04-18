import uuid

import pytest
from flask import json

from app.models import EMAIL_TYPE, SMS_TYPE, LETTER_TYPE, TEMPLATE_TYPES
from app.v2.template.template_schemas import (
    get_template_by_id_response,
    get_template_by_id_request,
    post_template_preview_request,
    post_template_preview_response
)
from app.schema_validation import validate
from jsonschema.exceptions import ValidationError


valid_json_get_response = {
    'id': str(uuid.uuid4()),
    'type': SMS_TYPE,
    'created_at': '2017-01-10T18:25:43.511Z',
    'updated_at': None,
    'version': 1,
    'created_by': 'someone@test.com',
    'body': 'some body'
}

valid_json_get_response_with_optionals = {
    'id': str(uuid.uuid4()),
    'type': EMAIL_TYPE,
    'created_at': '2017-01-10T18:25:43.511Z',
    'updated_at': None,
    'version': 1,
    'created_by': 'someone',
    'body': 'some body',
    'subject': "some subject"
}

valid_request_args = [{"id": str(uuid.uuid4()), "version": 1}, {"id": str(uuid.uuid4())}]

invalid_request_args = [
    ({"id": str(uuid.uuid4()), "version": "test"}, ["version test is not of type integer, null"]),
    ({"id": str(uuid.uuid4()), "version": 0}, ["version 0 is less than the minimum of 1"]),
    ({"version": 1}, ["id is a required property"]),
    ({"id": "invalid_uuid"}, ["id is not a valid UUID"]),
    ({"id": "invalid_uuid", "version": 0}, ["version 0 is less than the minimum of 1", "id is not a valid UUID"])
]

valid_json_post_args = {
    "id": str(uuid.uuid4()),
    "personalisation": {"key": "value"}
}

invalid_json_post_args = [
    ({"id": "invalid_uuid", "personalisation": {"key": "value"}}, ["id is not a valid UUID"]),
    ({"id": str(uuid.uuid4()), "personalisation": "invalid_personalisation"},
     ["personalisation should contain key value pairs"]),
    ({"personalisation": "invalid_personalisation"},
        ["id is a required property",
         "personalisation is a required property",
         "personalisation should contain key value pairs"])
]

valid_json_post_response = {
    'id': str(uuid.uuid4()),
    'type': 'email',
    'version': 1,
    'created_by': 'someone@test.com',
    'body': 'some body'
}

valid_json_post_response_with_optionals = {
    'id': str(uuid.uuid4()),
    'type': 'email',
    'version': 1,
    'created_by': 'someone@test.com',
    'body': "some body",
    'subject': 'some subject'
}


@pytest.mark.parametrize("args", valid_request_args)
def test_get_template_request_schema_against_valid_args_is_valid(args):
    assert validate(args, get_template_by_id_request) == args


@pytest.mark.parametrize("args,error_message", invalid_request_args)
def test_get_template_request_schema_against_invalid_args_is_invalid(args, error_message):
    with pytest.raises(ValidationError) as e:
        validate(args, get_template_by_id_request)
    errors = json.loads(str(e.value))

    assert errors['status_code'] == 400

    for error in errors['errors']:
        assert error['message'] in error_message


@pytest.mark.parametrize("template_type", TEMPLATE_TYPES)
@pytest.mark.parametrize("response", [valid_json_get_response, valid_json_get_response_with_optionals])
@pytest.mark.parametrize("updated_datetime", [None, '2017-01-11T18:25:43.511Z'])
def test_get_template_response_schema_is_valid(response, template_type, updated_datetime):
    if updated_datetime:
        response['updated_at'] = updated_datetime

    response['type'] = template_type

    assert validate(response, get_template_by_id_response) == response


def test_post_template_preview_against_valid_args_is_valid():
    assert validate(valid_json_post_args, post_template_preview_request) == valid_json_post_args


@pytest.mark.parametrize("args,error_message", invalid_json_post_args)
def test_post_template_preview_against_invalid_args_is_invalid(args, error_message):
    with pytest.raises(ValidationError) as e:
        validate(args, post_template_preview_request)
    errors = json.loads(str(e.value))

    assert errors['status_code'] == 400

    for error in errors['errors']:
        assert error['message'] in error_message


@pytest.mark.parametrize("template_type", TEMPLATE_TYPES)
@pytest.mark.parametrize("response", [valid_json_post_response, valid_json_post_response_with_optionals])
def test_post_template_preview_response_schema_is_valid(response, template_type):
    response['type'] = template_type

    assert validate(response, post_template_preview_response) == response
