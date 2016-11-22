import json

from jsonschema import (Draft4Validator, ValidationError, FormatChecker)
from notifications_utils.recipients import (validate_phone_number, validate_email_address, InvalidPhoneError,
                                            InvalidEmailError)


def validate(json_to_validate, schema):
    format_checker = FormatChecker()

    @format_checker.checks('phone_number', raises=InvalidPhoneError)
    def validate_schema_phone_number(instance):
        validate_phone_number(instance)
        return True

    @format_checker.checks('email_address', raises=InvalidEmailError)
    def validate_schema_email_address(instance):
        validate_email_address(instance)
        return True

    validator = Draft4Validator(schema, format_checker=format_checker)
    errors = list(validator.iter_errors(json_to_validate))
    if errors.__len__() > 0:
        raise ValidationError(build_error_message(errors))
    return json_to_validate


def build_error_message(errors):
    fields = []
    for e in errors:
        field = "{} {}".format(e.path[0], e.schema.get('validationMessage')) if e.schema.get(
            'validationMessage') else __format_message(e)
        fields.append({"error": "ValidationError", "message": field})
    message = {
        "status_code": 400,
        "errors": fields
    }

    return json.dumps(message)


def __format_message(e):
    s = e.message.split("'")
    msg = "{}{}".format(s[1], s[2])
    return msg if not e.cause else "{} {}".format(e.path[0], e.cause.message)
