import uuid

import pytest
from flask import json

from app.v2.template.template_schemas import (
    get_template_by_id_response,
    get_template_by_id_request
)
from app.schema_validation import validate
from jsonschema.exceptions import ValidationError


valid_json = {
    'id': str(uuid.uuid4()),
    'type': 'email',
    'created_at': '2017-01-10T18:25:43.511Z',
    'updated_at': '2017-04-23T18:25:43.511Z',
    'version': 1,
    'created_by': 'someone@test.com',
    'body': "some body"
}

valid_json_with_optionals = {
    'id': str(uuid.uuid4()),
    'type': 'email',
    'created_at': '2017-01-10T18:25:43.511Z',
    'updated_at': '2017-04-23T18:25:43.511Z',
    'version': 1,
    'created_by': 'someone',
    'body': "some body",
    'subject': "some subject"
}

valid_request_args = [
    {"id": str(uuid.uuid4()), "version": 1}, {"id": str(uuid.uuid4())}]

invalid_request_args = [
    ({"id": str(uuid.uuid4()), "version": "test"}, ["version test is not of type integer, null"]),
    ({"id": str(uuid.uuid4()), "version": 0}, ["version 0 is less than the minimum of 1"]),
    ({"version": 1}, ["id is a required property"]),
    ({"id": "invalid_uuid"}, ["id is not a valid UUID"]),
    ({"id": "invalid_uuid", "version": 0}, ["version 0 is less than the minimum of 1", "id is not a valid UUID"])
]


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


@pytest.mark.parametrize("response", [valid_json, valid_json_with_optionals])
def test_get_template_response_schema_is_valid(response):
    assert validate(response, get_template_by_id_response) == response
