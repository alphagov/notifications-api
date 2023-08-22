import json
import re
from datetime import datetime, timedelta
from uuid import UUID

from iso8601 import ParseError, iso8601
from jsonschema import Draft7Validator, FormatChecker, ValidationError
from notifications_utils.recipients import (
    InvalidEmailError,
    InvalidPhoneError,
    validate_email_address,
    validate_phone_number,
)

from app.notifications.validators import remap_phone_number_validation_messages

format_checker = FormatChecker()


@format_checker.checks("validate_uuid", raises=Exception)
def validate_uuid(instance):
    if isinstance(instance, str):
        UUID(instance)
    return True


@format_checker.checks("phone_number", raises=InvalidPhoneError)
def validate_schema_phone_number(instance):
    if isinstance(instance, str):
        try:
            validate_phone_number(instance, international=True)
        except InvalidPhoneError as error:
            raise InvalidPhoneError(remap_phone_number_validation_messages(str(error))) from error
    return True


@format_checker.checks("email_address", raises=InvalidEmailError)
def validate_schema_email_address(instance):
    if isinstance(instance, str):
        validate_email_address(instance)
    return True


@format_checker.checks("postage", raises=ValidationError)
def validate_schema_postage(instance):
    if isinstance(instance, str):
        if instance not in ["first", "second", "europe", "rest-of-world"]:
            raise ValidationError("invalid. It must be first, second, europe or rest-of-world.")
    return True


@format_checker.checks("datetime_within_next_day", raises=ValidationError)
def validate_schema_date_with_hour(instance):
    if isinstance(instance, str):
        try:
            dt = iso8601.parse_date(instance).replace(tzinfo=None)
            if dt < datetime.utcnow():
                raise ValidationError("datetime can not be in the past")
            if dt > datetime.utcnow() + timedelta(hours=24):
                raise ValidationError("datetime can only be 24 hours in the future")
        except ParseError as e:
            raise ValidationError(
                "datetime format is invalid. It must be a valid ISO8601 date time format, "
                "https://en.wikipedia.org/wiki/ISO_8601"
            ) from e
    return True


@format_checker.checks("send_a_file_retention_period", raises=ValidationError)
def validate_schema_retention_period(instance):
    if instance is None:
        return True

    if isinstance(instance, str):
        period = instance.strip().lower()
        match = re.match(r"^(\d+) weeks?$", period)
        if match and 1 <= int(match.group(1)) <= 78:
            return True

    raise ValidationError(
        f"Unsupported value for retention_period: {instance}. Supported periods are from 1 to 78 weeks."
    )


@format_checker.checks("send_a_file_is_csv", raises=ValidationError)
def send_a_file_is_csv(instance):
    if instance is None or isinstance(instance, bool):
        return True

    raise ValidationError(f"Unsupported value for is_csv: {instance}. Use a boolean true or false value.")


@format_checker.checks("send_a_file_confirm_email_before_download", raises=ValidationError)
def send_a_file_confirm_email_before_download(instance):
    if instance is None or isinstance(instance, bool):
        return True

    raise ValidationError(
        f"Unsupported value for confirm_email_before_download: {instance}. Use a boolean true or false value."
    )


@format_checker.checks("datetime", raises=ValidationError)
def validate_schema_datetime(instance):
    if isinstance(instance, str):
        try:
            iso8601.parse_date(instance)
        except ParseError as e:
            raise ValidationError(
                "datetime format is invalid. It must be a valid ISO8601 date time format, "
                "https://en.wikipedia.org/wiki/ISO_8601"
            ) from e
    return True


def validate(json_to_validate, schema):
    validator = Draft7Validator(schema, format_checker=format_checker)
    errors = list(validator.iter_errors(json_to_validate))
    if errors.__len__() > 0:
        raise ValidationError(build_error_message(errors))
    return json_to_validate


def build_error_message(errors):
    fields = []
    for e in errors:
        field = (
            "{} {}".format(e.path[0], e.schema["validationMessage"])
            if "validationMessage" in e.schema
            else __format_message(e)
        )
        fields.append({"error": "ValidationError", "message": field})
    message = {"status_code": 400, "errors": unique_errors(fields)}

    return json.dumps(message)


def unique_errors(dups):
    unique = []
    for x in dups:
        if x not in unique:
            unique.append(x)
    return unique


def __format_message(e):
    def get_path(e):
        error_path = None
        try:
            error_path = e.path.popleft()
            # no need to catch IndexError exception explicity as
            # error_path is None if e.path has no items
        except Exception:
            pass
        return error_path

    def get_error_message(e):
        # e.cause is an exception (such as InvalidPhoneError). if it's not present it was a standard jsonschema error
        # such as a required field not being present
        error_message = str(e.cause) if e.cause else e.message
        return error_message.replace("'", "")

    path = get_path(e)
    message = get_error_message(e)
    if path:
        return "{} {}".format(path, message)
    else:
        return "{}".format(message)
