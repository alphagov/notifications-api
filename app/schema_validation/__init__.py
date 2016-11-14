import json

from jsonschema import (Draft4Validator, ValidationError, FormatChecker)
from notifications_utils.recipients import (validate_phone_number, validate_email_address)


def validate(json_to_validate, schema):
    format_checker = FormatChecker()

    @format_checker.checks('phone_number')
    def validate_schema_phone_number(instance):
        return validate_phone_number(instance)

    @format_checker.checks('email_address')
    def validate_schema_email_address(instance):
        return validate_email_address(instance)

    validator = Draft4Validator(schema, format_checker=format_checker)
    errors = list(validator.iter_errors(json_to_validate))
    if errors.__len__() > 0:
        raise ValidationError(build_error_message(errors, schema))
    return json_to_validate


def build_error_message(errors, schema):
    fields = []
    for e in errors:
        field = "'{}' {}".format(e.path[0], e.schema.get('validationMessage')) if e.schema.get(
            'validationMessage') else e.message
        s = field.split("'")
        field = {"error": "ValidationError", "message": "{}{}".format(s[1], s[2])}
        fields.append(field)
    message = {
        "status_code": 400,
        "errors": fields
    }

    return json.dumps(message)
