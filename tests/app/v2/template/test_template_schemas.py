import uuid

import pytest
from flask import json

from app.models import EMAIL_TYPE, SMS_TYPE, TEMPLATE_TYPES
from app.v2.template.template_schemas import (
    get_template_by_id_response,
    get_template_by_id_request,
    post_template_preview_request,
    post_template_preview_response,
    get_all_template_request,
    get_all_template_response
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
     ["id is a required property", "personalisation should contain key value pairs"])
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

valid_json_get_all_response = [
    {
        'links': {'self': 'http://some.path', 'next': 'http://some.other.path'},
        "templates": [
            {"id": str(uuid.uuid4()), "version": 1, "uri": "http://template/id"},
            {"id": str(uuid.uuid4()), "version": 2, "uri": "http://template/id"}
        ]
    },
    {
        'links': {'self': 'http://some.path'},
        "templates": [{"id": str(uuid.uuid4()), "version": 1, "uri": "http://template/id"}]
    },
    {
        'links': {'self': 'http://some.path'},
        "templates": []
    }
]

invalid_json_get_all_response = [
    ({
        'links': {'self': 'invalid_uri'},
        "templates": [
            {"id": str(uuid.uuid4()), "version": 1, "uri": "http://template/id"}
        ]
    }, ['links invalid_uri is not a valid URI.']),
    ({
        'links': {'self': 'http://some.path'},
        "templates": [
            {"id": 'invalid_id', "version": 1, "uri": "http://template/id"}
        ]
    }, ['templates is not a valid UUID']),
    ({
        'links': {'self': 'http://some.path'},
        "templates": [
            {"id": str(uuid.uuid4()), "version": 'invalid_version', "uri": "http://template/id"}
        ]
    }, ['templates invalid_version is not of type integer']),
    ({
        'links': {'self': 'http://some.path'},
        "templates": [
            {"id": str(uuid.uuid4()), "version": 1, "uri": "invalid_uri"}
        ]
    }, ['templates invalid_uri is not a valid URI.']),
    ({
        'links': {'self': 'http://some.path'}
    }, ['templates is a required property']),
    ({
        'links': {'next': 'http://some.other.path'},
        "templates": [{"id": str(uuid.uuid4()), "version": 1, "uri": "http://template/id"}]
    }, ['links self is a required property']),
    ({
        'links': {'self': 'http://some.path', 'next': 'http://some.other.path'},
        "templates": [{"version": 1, "uri": "http://template/id"}]
    }, ['templates id is a required property']),
    ({
        'links': {'self': 'http://some.path', 'next': 'http://some.other.path'},
        "templates": [{"id": str(uuid.uuid4()), "uri": "http://template/id"}]
    }, ['templates version is a required property']),
    ({
        'links': {'self': 'http://some.path', 'next': 'http://some.other.path'},
        "templates": [{"id": str(uuid.uuid4()), "version": 1}]
    }, ['templates uri is a required property']),
    ({
        'links': {'self': 'http://some.path', 'next': 'http://some.other.path'},
        "templates": [{"version": 1}]
    }, ['templates id is a required property', 'templates uri is a required property']),
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


@pytest.mark.parametrize("args,error_messages", invalid_json_post_args)
def test_post_template_preview_against_invalid_args_is_invalid(args, error_messages):
    with pytest.raises(ValidationError) as e:
        validate(args, post_template_preview_request)
    errors = json.loads(str(e.value))

    assert errors['status_code'] == 400
    assert len(errors['errors']) == len(error_messages)
    for error in errors['errors']:
        assert error['message'] in error_messages


@pytest.mark.parametrize("template_type", TEMPLATE_TYPES)
@pytest.mark.parametrize("response", [valid_json_post_response, valid_json_post_response_with_optionals])
def test_post_template_preview_response_schema_is_valid(response, template_type):
    response['type'] = template_type

    assert validate(response, post_template_preview_response) == response


@pytest.mark.parametrize("template_type", TEMPLATE_TYPES)
def test_get_all_template_request_schema_against_valid_args_is_valid(template_type):
    data = {'type': template_type}
    assert validate(data, get_all_template_request) == data


@pytest.mark.parametrize("response", valid_json_get_all_response)
def test_valid_get_all_templates_response_schema_is_valid(response):
    assert validate(response, get_all_template_response) == response


@pytest.mark.parametrize("response,error_messages", invalid_json_get_all_response)
def test_invalid_get_all_templates_response_schema_is_invalid(response, error_messages):
    with pytest.raises(ValidationError) as e:
        validate(response, get_all_template_response)
    errors = json.loads(str(e.value))

    assert errors['status_code'] == 400
    assert len(errors['errors']) == len(error_messages)
    for error in errors['errors']:
        assert error['message'] in error_messages
