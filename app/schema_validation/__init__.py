import json
from datetime import datetime

from jsonschema import (Draft4Validator, ValidationError, FormatChecker)
from notifications_utils.recipients import (validate_phone_number, validate_email_address, InvalidPhoneError,
                                            InvalidEmailError)


def validate(json_to_validate, schema):
    format_checker = FormatChecker()

    @format_checker.checks('phone_number', raises=InvalidPhoneError)
    def validate_schema_phone_number(instance):
        if isinstance(instance, str):
            validate_phone_number(instance, international=True)
        return True

    @format_checker.checks('email_address', raises=InvalidEmailError)
    def validate_schema_email_address(instance):
        if isinstance(instance, str):
            validate_email_address(instance)
        return True

    @format_checker.checks('datetime', raises=ValidationError)
    def validate_schema_date_with_hour(instance):
        if isinstance(instance, str):
            try:
                datetime.strptime(instance, "%Y-%m-%d %H")
            except ValueError as e:
                raise ValidationError("datetime format is invalid. Use the format: "
                                      "YYYY-MM-DD HH, for example 2017-05-30 13")
        return True

    validator = Draft4Validator(schema, format_checker=format_checker)
    errors = list(validator.iter_errors(json_to_validate))
    if errors.__len__() > 0:
        raise ValidationError(build_error_message(errors))
    return json_to_validate


def build_error_message(errors):
    fields = []
    for e in errors:
        field = (
            "{} {}".format(e.path[0], e.schema['validationMessage'])
            if 'validationMessage' in e.schema else __format_message(e)
        )
        fields.append({"error": "ValidationError", "message": field})
    message = {
        "status_code": 400,
        "errors": fields
    }

    return json.dumps(message)


def __format_message(e):
    def get_path(e):
        error_path = None
        try:
            error_path = e.path.popleft()
            # no need to catch IndexError exception explicity as
            # error_path is None if e.path has no items
        finally:
            return error_path

    def get_error_message(e):
        # e.cause is an exception (such as InvalidPhoneError). if it's not present it was a standard jsonschema error
        # such as a required field not being present
        error_message = str(e.cause) if e.cause else e.message
        return error_message.replace("'", '')

    path = get_path(e)
    message = get_error_message(e)
    if path:
        return "{} {}".format(path, message)
    else:
        return "{}".format(message)
