import uuid

import pytest
from flask import json

from app.models import EMAIL_TYPE, SMS_TYPE, TEMPLATE_TYPES
from app.v2.templates.templates_schemas import (
    get_all_template_request,
    get_all_template_response
)
from app.schema_validation import validate
from jsonschema.exceptions import ValidationError


valid_json_get_all_response = [
    {
        'links': {'current': 'http://some.path', 'next': 'http://some.other.path'},
        "templates": [
            {"id": str(uuid.uuid4()), "version": 1, "uri": "http://template/id"},
            {"id": str(uuid.uuid4()), "version": 2, "uri": "http://template/id"}
        ]
    },
    {
        'links': {'current': 'http://some.path'},
        "templates": [{"id": str(uuid.uuid4()), "version": 1, "uri": "http://template/id"}]
    },
    {
        'links': {'current': 'http://some.path'},
        "templates": []
    }
]

invalid_json_get_all_response = [
    ({
        'links': {'current': 'invalid_uri'},
        "templates": [
            {"id": str(uuid.uuid4()), "version": 1, "uri": "http://template/id"}
        ]
    }, ['links invalid_uri is not a valid URI.']),
    ({
        'links': {'current': 'http://some.path'},
        "templates": [
            {"id": 'invalid_id', "version": 1, "uri": "http://template/id"}
        ]
    }, ['templates is not a valid UUID']),
    ({
        'links': {'current': 'http://some.path'},
        "templates": [
            {"id": str(uuid.uuid4()), "version": 'invalid_version', "uri": "http://template/id"}
        ]
    }, ['templates invalid_version is not of type integer']),
    ({
        'links': {'current': 'http://some.path'},
        "templates": [
            {"id": str(uuid.uuid4()), "version": 1, "uri": "invalid_uri"}
        ]
    }, ['templates invalid_uri is not a valid URI.']),
    ({
        'links': {'current': 'http://some.path'}
    }, ['templates is a required property']),
    ({
        'links': {'next': 'http://some.other.path'},
        "templates": [{"id": str(uuid.uuid4()), "version": 1, "uri": "http://template/id"}]
    }, ['links current is a required property']),
    ({
        'links': {'current': 'http://some.path', 'next': 'http://some.other.path'},
        "templates": [{"version": 1, "uri": "http://template/id"}]
    }, ['templates id is a required property']),
    ({
        'links': {'current': 'http://some.path', 'next': 'http://some.other.path'},
        "templates": [{"id": str(uuid.uuid4()), "uri": "http://template/id"}]
    }, ['templates version is a required property']),
    ({
        'links': {'current': 'http://some.path', 'next': 'http://some.other.path'},
        "templates": [{"id": str(uuid.uuid4()), "version": 1}]
    }, ['templates uri is a required property']),
    ({
        'links': {'current': 'http://some.path', 'next': 'http://some.other.path'},
        "templates": [{"version": 1}]
    }, ['templates id is a required property', 'templates uri is a required property']),
]


@pytest.mark.parametrize("template_type", TEMPLATE_TYPES)
def test_get_all_template_request_schema_against_no_args_is_valid(template_type):
    data = {}
    assert validate(data, get_all_template_request) == data


@pytest.mark.parametrize("template_type", TEMPLATE_TYPES)
def test_get_all_template_request_schema_against_valid_args_is_valid(template_type):
    data = {'type': template_type}
    assert validate(data, get_all_template_request) == data


@pytest.mark.parametrize("template_type", TEMPLATE_TYPES)
def test_get_all_template_request_schema_against_valid_args_with_optional_is_valid(template_type, fake_uuid):
    data = {'type': template_type, 'older_than': fake_uuid}
    assert validate(data, get_all_template_request) == data


@pytest.mark.parametrize("template_type", TEMPLATE_TYPES)
def test_get_all_template_request_schema_against_invalid_args_is_invalid(template_type):
    data = {'type': 'unknown'}

    with pytest.raises(ValidationError) as e:
        validate(data, get_all_template_request)
    errors = json.loads(str(e.value))

    assert errors['status_code'] == 400
    assert len(errors['errors']) == 1
    assert errors['errors'][0]['message'] == 'type unknown is not one of [sms, email, letter]'


@pytest.mark.parametrize("template_type", TEMPLATE_TYPES)
def test_get_all_template_request_schema_against_invalid_args_with_optional_is_invalid(template_type):
    data = {'type': template_type, 'older_than': 'invalid_uuid'}

    with pytest.raises(ValidationError) as e:
        validate(data, get_all_template_request)
    errors = json.loads(str(e.value))

    assert errors['status_code'] == 400
    assert len(errors['errors']) == 1
    assert errors['errors'][0]['message'] == 'older_than is not a valid UUID'


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
