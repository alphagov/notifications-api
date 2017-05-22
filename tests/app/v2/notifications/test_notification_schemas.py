import uuid

import pytest
from flask import json
from jsonschema import ValidationError

from app.v2.notifications.notification_schemas import (
    get_notifications_request,
    get_notification_response,
    post_sms_request as post_sms_request_schema,
    post_sms_response as post_sms_response_schema,
    post_email_request as post_email_request_schema,
    post_email_response as post_email_response_schema
)
from app.schema_validation import validate


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
        "[created, sending, sent, delivered, pending, failed, " \
        "technical-failure, temporary-failure, permanent-failure]"

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
        assert "status {} is not one of [created, sending, sent, delivered, " \
            "pending, failed, technical-failure, temporary-failure, permanent-failure]".format(
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
                                'message': "personalisation should contain key value pairs"}]
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


def valid_sms_response():
    return {
        "id": str(uuid.uuid4()),
        "content": {"body": "contents of message",
                    "from_number": "46045"},
        "uri": "http://notify.api/v2/notifications/id",
        "template": {
            "id": str(uuid.uuid4()),
            "version": 1,
            "uri": "http://notify.api/v2/template/id"
        }
    }


def valid_sms_response_with_optionals():
    return {
        "id": str(uuid.uuid4()),
        "reference": "reference_from_service",
        "content": {"body": "contents of message",
                    "from_number": "46045"},
        "uri": "http://notify.api/v2/notifications/id",
        "template": {
            "id": str(uuid.uuid4()),
            "version": 1,
            "uri": "http://notify.api/v2/template/id"
        }
    }


@pytest.mark.parametrize('input', [valid_sms_response()])
def test_post_sms_response_schema_schema_is_valid(input):
    assert validate(input, post_sms_response_schema) == input


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


def valid_email_response_with_optionals():
    return {
        "id": str(uuid.uuid4()),
        "reference": "some reference",
        "content": {"body": "the body of the message",
                    "subject": "subject of the message",
                    "from_email": "service@dig.gov.uk"},
        "uri": "http://notify.api/v2/notifications/id",
        "template": {
            "id": str(uuid.uuid4()),
            "version": 1,
            "uri": "http://notify.api/v2/template/id"
        },
        "schedule_for": "2017-05-12 13:00:00"
    }


@pytest.mark.parametrize("input", [valid_email_response(), valid_email_response_with_optionals()])
def test_post_email_response_schema(input):
    assert validate(input, post_email_response_schema) == input


@pytest.mark.parametrize('response, schema', [
    (valid_email_response(), post_email_response_schema),
    (valid_sms_response(), post_sms_response_schema)
])
def test_post_sms_response_schema_missing_uri_raises_validation_error(response, schema):
    del response['uri']
    with pytest.raises(ValidationError) as e:
        validate(response, schema)
    error = json.loads(str(e.value))
    assert error['status_code'] == 400
    assert error['errors'] == [{'error': 'ValidationError',
                               'message': "uri is a required property"}]


@pytest.mark.parametrize('response, schema', [
    (valid_email_response(), post_email_response_schema),
    (valid_sms_response(), post_sms_response_schema)
])
def test_post_sms_response_schema_invalid_uri_raises_validation_error(response, schema):
    response['uri'] = 'invalid-uri'
    with pytest.raises(ValidationError) as e:
        validate(response, schema)
    error = json.loads(str(e.value))
    assert error['status_code'] == 400
    assert error['errors'] == [{'error': 'ValidationError',
                               'message': "uri invalid-uri is not a valid URI."}]


@pytest.mark.parametrize('response, schema', [
    (valid_email_response(), post_email_response_schema),
    (valid_sms_response(), post_sms_response_schema)
])
def test_post_sms_response_schema_missing_template_uri_raises_validation_error(response, schema):
    del response['template']['uri']
    with pytest.raises(ValidationError) as e:
        validate(response, schema)
    error = json.loads(str(e.value))
    assert error['status_code'] == 400
    assert error['errors'] == [{'error': 'ValidationError',
                               'message': "template uri is a required property"}]


@pytest.mark.parametrize('response, schema', [
    (valid_email_response(), post_email_response_schema),
    (valid_sms_response(), post_sms_response_schema)
])
def test_post_sms_response_schema_invalid_template_uri_raises_validation_error(response, schema):
    response['template']['uri'] = 'invalid-uri'
    with pytest.raises(ValidationError) as e:
        validate(response, schema)
    error = json.loads(str(e.value))
    assert error['status_code'] == 400
    assert error['errors'] == [{'error': 'ValidationError',
                               'message': "template invalid-uri is not a valid URI."}]


def test_get_notifications_response_with_email_and_phone_number():
    response = {"id": str(uuid.uuid4()),
                "reference": "something",
                "email_address": None,
                "phone_number": "+447115411111",
                "line_1": None,
                "line_2": None,
                "line_3": None,
                "line_4": None,
                "line_5": None,
                "line_6": None,
                "postcode": None,
                "type": "email",
                "status": "delivered",
                "template": {"id": str(uuid.uuid4()), "version": 1, "uri": "http://template/id"},
                "body": "some body",
                "subject": "some subject",
                "created_at": "2016-01-01",
                "sent_at": "2016-01-01",
                "completed_at": "2016-01-01",
                "schedule_for": ""
                }

    assert validate(response, get_notification_response) == response


@pytest.mark.parametrize("schema",
                         [post_email_request_schema, post_sms_request_schema])
def test_post_schema_valid_scheduled_for(schema):
    j = {"template_id": str(uuid.uuid4()),
         "email_address": "joe@gmail.com",
         "scheduled_for": "2017-05-12 13:15"}
    if schema == post_email_request_schema:
        j.update({"email_address": "joe@gmail.com"})
    else:
        j.update({"phone_number": "07515111111"})
    assert validate(j, schema) == j


@pytest.mark.parametrize("invalid_datetime",
                         ["2017-05-12 13:00:00", "13:00:00 2017-01-01"])
@pytest.mark.parametrize("schema",
                         [post_email_request_schema, post_sms_request_schema])
def test_post_email_schema_invalid_scheduled_for(invalid_datetime, schema):
    j = {"template_id": str(uuid.uuid4()),
         "scheduled_for": invalid_datetime}
    if schema == post_email_request_schema:
        j.update({"email_address": "joe@gmail.com"})
    else:
        j.update({"phone_number": "07515111111"})
    with pytest.raises(ValidationError) as e:
        validate(j, schema)
    error = json.loads(str(e.value))
    assert error['status_code'] == 400
    assert error['errors'] == [{'error': 'ValidationError',
                                'message': "scheduled_for datetime format is invalid. Use the format: "
                                           "YYYY-MM-DD HH:MI, for example 2017-05-30 13:15"}]
