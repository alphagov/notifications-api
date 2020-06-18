import uuid

import pytest
from flask import json
from jsonschema import ValidationError

from app.models import NOTIFICATION_CREATED, EMAIL_TYPE
from app.schema_validation import validate
from app.v2.notifications.notification_schemas import (
    get_notifications_request,
    post_sms_request as post_sms_request_schema,
    post_email_request as post_email_request_schema
)


valid_get_json = {}

valid_get_with_optionals_json = {
    "reference": "test reference",
    "status": [NOTIFICATION_CREATED],
    "template_type": [EMAIL_TYPE],
    "include_jobs": "true",
    "older_than": "a5149c32-f03b-4711-af49-ad6993797d45"
}


@pytest.mark.parametrize("input", [valid_get_json, valid_get_with_optionals_json])
def test_get_notifications_valid_json(input):
    assert validate(input, get_notifications_request) == input


@pytest.mark.parametrize('invalid_statuses, valid_statuses', [
    # one invalid status
    (["elephant"], []),
    # multiple invalid statuses
    (["elephant", "giraffe", "cheetah"], []),
    # one bad status and one good status
    (["elephant"], ["created"]),
])
def test_get_notifications_request_invalid_statuses(
        invalid_statuses, valid_statuses
):
    partial_error_status = "is not one of " \
        "[cancelled, created, sending, sent, delivered, pending, failed, " \
        "technical-failure, temporary-failure, permanent-failure, pending-virus-check, " \
        "validation-failed, virus-scan-failed, returned-letter, accepted, received]"

    with pytest.raises(ValidationError) as e:
        validate({'status': invalid_statuses + valid_statuses}, get_notifications_request)

    errors = json.loads(str(e.value)).get('errors')
    assert len(errors) == len(invalid_statuses)
    for index, value in enumerate(invalid_statuses):
        assert errors[index]['message'] == "status {} {}".format(value, partial_error_status)


@pytest.mark.parametrize('invalid_template_types, valid_template_types', [
    # one invalid template_type
    (["orange"], []),
    # multiple invalid template_types
    (["orange", "avocado", "banana"], []),
    # one bad template_type and one good template_type
    (["orange"], ["sms"]),
])
def test_get_notifications_request_invalid_template_types(
        invalid_template_types, valid_template_types
):
    partial_error_template_type = "is not one of [sms, email, letter]"

    with pytest.raises(ValidationError) as e:
        validate({'template_type': invalid_template_types + valid_template_types}, get_notifications_request)

    errors = json.loads(str(e.value)).get('errors')
    assert len(errors) == len(invalid_template_types)
    for index, value in enumerate(invalid_template_types):
        assert errors[index]['message'] == "template_type {} {}".format(value, partial_error_template_type)


def test_get_notifications_request_invalid_statuses_and_template_types():
    with pytest.raises(ValidationError) as e:
        validate({
            'status': ["created", "elephant", "giraffe"],
            'template_type': ["sms", "orange", "avocado"]
        }, get_notifications_request)

    errors = json.loads(str(e.value)).get('errors')

    assert len(errors) == 4

    error_messages = [error['message'] for error in errors]
    for invalid_status in ["elephant", "giraffe"]:
        assert "status {} is not one of [cancelled, created, sending, sent, delivered, " \
            "pending, failed, technical-failure, temporary-failure, permanent-failure, " \
            "pending-virus-check, validation-failed, virus-scan-failed, returned-letter, accepted, received]".format(
                invalid_status
            ) in error_messages

    for invalid_template_type in ["orange", "avocado"]:
        assert "template_type {} is not one of [sms, email, letter]" \
            .format(invalid_template_type) in error_messages


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
    assert validate(input, post_sms_request_schema) == input


@pytest.mark.parametrize("template_id",
                         ['2ebe4da8-17be-49fe-b02f-dff2760261a0' + "\n",
                          '2ebe4da8-17be-49fe-b02f-dff2760261a0' + " ",
                          '2ebe4da8-17be-49fe-b02f-dff2760261a0' + "\r",
                          "\t" + '2ebe4da8-17be-49fe-b02f-dff2760261a0',
                          '2ebe4da8-17be-49fe-b02f-dff2760261a0'[4:],
                          "bad_uuid"
                          ]
                         )
def test_post_sms_json_schema_bad_uuid(template_id):
    j = {
        "template_id": template_id,
        "phone_number": "07515111111"
    }
    with pytest.raises(ValidationError) as e:
        validate(j, post_sms_request_schema)
    error = json.loads(str(e.value))
    assert len(error.keys()) == 2
    assert error.get('status_code') == 400
    assert len(error.get('errors')) == 1
    assert {'error': 'ValidationError',
            'message': "template_id is not a valid UUID"} in error['errors']


def test_post_sms_json_schema_bad_uuid_and_missing_phone_number():
    j = {"template_id": "notUUID"}
    with pytest.raises(ValidationError) as e:
        validate(j, post_sms_request_schema)
    error = json.loads(str(e.value))
    assert len(error.keys()) == 2
    assert error.get('status_code') == 400
    assert len(error.get('errors')) == 2
    assert {'error': 'ValidationError',
            'message': "phone_number is a required property"} in error['errors']
    assert {'error': 'ValidationError',
            'message': "template_id is not a valid UUID"} in error['errors']


def test_post_sms_schema_with_personalisation_that_is_not_a_dict():
    j = {
        "phone_number": "07515111111",
        "template_id": str(uuid.uuid4()),
        "reference": "reference from caller",
        "personalisation": "not_a_dict"
    }
    with pytest.raises(ValidationError) as e:
        validate(j, post_sms_request_schema)
    error = json.loads(str(e.value))
    assert len(error.get('errors')) == 1
    assert error['errors'] == [{'error': 'ValidationError',
                                'message': "personalisation not_a_dict is not of type object"}]
    assert error.get('status_code') == 400
    assert len(error.keys()) == 2


@pytest.mark.parametrize('invalid_phone_number, err_msg', [
    ('08515111111', 'phone_number Not a UK mobile number'),
    ('07515111*11', 'phone_number Must not contain letters or symbols'),
    ('notaphoneumber', 'phone_number Must not contain letters or symbols'),
    (7700900001, 'phone_number 7700900001 is not of type string'),
    (None, 'phone_number None is not of type string'),
    ([], 'phone_number [] is not of type string'),
    ({}, 'phone_number {} is not of type string'),
])
def test_post_sms_request_schema_invalid_phone_number(invalid_phone_number, err_msg):
    j = {"phone_number": invalid_phone_number,
         "template_id": str(uuid.uuid4())
         }
    with pytest.raises(ValidationError) as e:
        validate(j, post_sms_request_schema)
    errors = json.loads(str(e.value)).get('errors')
    assert len(errors) == 1
    assert {"error": "ValidationError", "message": err_msg} == errors[0]


def test_post_sms_request_schema_invalid_phone_number_and_missing_template():
    j = {"phone_number": '08515111111',
         }
    with pytest.raises(ValidationError) as e:
        validate(j, post_sms_request_schema)
    errors = json.loads(str(e.value)).get('errors')
    assert len(errors) == 2
    assert {"error": "ValidationError", "message": "phone_number Not a UK mobile number"} in errors
    assert {"error": "ValidationError", "message": "template_id is a required property"} in errors


valid_post_email_json = {"email_address": "test@example.gov.uk",
                         "template_id": str(uuid.uuid4())
                         }
valid_post_email_json_with_optionals = {
    "email_address": "test@example.gov.uk",
    "template_id": str(uuid.uuid4()),
    "reference": "reference from caller",
    "personalisation": {"key": "value"}
}


@pytest.mark.parametrize("input", [valid_post_email_json, valid_post_email_json_with_optionals])
def test_post_email_schema_is_valid(input):
    assert validate(input, post_email_request_schema) == input


def test_post_email_schema_bad_uuid_and_missing_email_address():
    j = {"template_id": "bad_template"}
    with pytest.raises(ValidationError):
        validate(j, post_email_request_schema)


@pytest.mark.parametrize('email_address, err_msg', [
    ('example', 'email_address Not a valid email address'),
    (12345, 'email_address 12345 is not of type string'),
    ('with(brackets)@example.com', 'email_address Not a valid email address'),
    (None, 'email_address None is not of type string'),
    ([], 'email_address [] is not of type string'),
    ({}, 'email_address {} is not of type string'),
])
def test_post_email_schema_invalid_email_address(email_address, err_msg):
    j = {"template_id": str(uuid.uuid4()), "email_address": email_address}
    with pytest.raises(ValidationError) as e:
        validate(j, post_email_request_schema)

    errors = json.loads(str(e.value)).get('errors')
    assert len(errors) == 1
    assert {"error": "ValidationError", "message": err_msg} == errors[0]


def valid_email_response():
    return {
        "id": str(uuid.uuid4()),
        "content": {"body": "the body of the message",
                    "subject": "subject of the message",
                    "from_email": "service@dig.gov.uk"},
        "uri": "http://notify.api/v2/notifications/id",
        "template": {
            "id": str(uuid.uuid4()),
            "version": 1,
            "uri": "http://notify.api/v2/template/id"
        },
        "scheduled_for": ""
    }
