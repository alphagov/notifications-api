import json
import re
from datetime import datetime, timedelta
from uuid import UUID

from iso8601 import ParseError, iso8601
from jsonschema import Draft7Validator, FormatChecker, ValidationError
from notifications_utils.recipient_validation.email_address import validate_email_address
from notifications_utils.recipient_validation.errors import InvalidEmailError, InvalidPhoneError, InvalidRecipientError
from notifications_utils.recipient_validation.phone_number import PhoneNumber

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
            number = PhoneNumber(instance)
            number.validate(
                allow_international_number=True,
                allow_uk_landline=True,
            )
        except InvalidPhoneError as e:
            raise e
    return True


@format_checker.checks("email_address", raises=InvalidEmailError)
def validate_schema_email_address(instance):
    if isinstance(instance, str):
        validate_email_address(instance)
    return True


@format_checker.checks("postage", raises=InvalidRecipientError)
def validate_schema_postage(instance):
    """
    For validating postage on templates and user requests, where postage can only be `first` or `second`
    """
    if isinstance(instance, str):
        if instance not in ["first", "second"]:
            raise InvalidRecipientError(message="invalid. It must be either first or second.")
    return True


@format_checker.checks("postage_including_international", raises=InvalidRecipientError)
def validate_schema_postage_including_international(instance):
    """
    For validating postage sent by admin when sending a precompiled letter, where postage can include international
    """
    if isinstance(instance, str):
        if instance not in ["first", "second", "europe", "rest-of-world"]:
            raise InvalidRecipientError(message="invalid. It must be first, second, europe or rest-of-world.")
    return True


@format_checker.checks("datetime_within_next_day", raises=InvalidRecipientError)
def validate_schema_date_with_hour(instance):
    if isinstance(instance, str):
        try:
            dt = iso8601.parse_date(instance).replace(tzinfo=None)
            if dt < datetime.utcnow():
                raise InvalidRecipientError(message="datetime can not be in the past")
            if dt > datetime.utcnow() + timedelta(hours=24):
                raise InvalidRecipientError(message="datetime can only be 24 hours in the future")
        except ParseError as e:
            raise InvalidRecipientError(
                message="datetime format is invalid. It must be a valid ISO8601 date time format, "
                "https://en.wikipedia.org/wiki/ISO_8601"
            ) from e
    return True


@format_checker.checks("send_a_file_retention_period", raises=InvalidRecipientError)
def validate_schema_retention_period(instance):
    if instance is None:
        return True

    if isinstance(instance, str):
        period = instance.strip().lower()
        match = re.match(r"^(\d+) weeks?$", period)
        if match and 1 <= int(match.group(1)) <= 78:
            return True

    raise InvalidRecipientError(
        message=f"Unsupported value for retention_period: {instance}. Supported periods are from 1 to 78 weeks."
    )


@format_checker.checks("send_a_file_filename", raises=InvalidRecipientError)
def validate_send_a_file_filename(instance):
    if instance is None:
        return True

    if isinstance(instance, str):
        if "." in instance:
            return True

    raise ValidationError(message="`filename` must end with a file extension. For example, filename.csv")


@format_checker.checks("send_a_file_is_csv", raises=InvalidRecipientError)
def send_a_file_is_csv(instance):
    if instance is None or isinstance(instance, bool):
        return True

    raise ValidationError(message=f"Unsupported value for is_csv: {instance}. Use a boolean true or false value.")


@format_checker.checks("send_a_file_confirm_email_before_download", raises=InvalidRecipientError)
def send_a_file_confirm_email_before_download(instance):
    if instance is None or isinstance(instance, bool):
        return True

    raise InvalidRecipientError(
        message=f"Unsupported value for confirm_email_before_download: {instance}. Use a boolean true or false value."
    )


@format_checker.checks("letter_production_run_date", raises=InvalidRecipientError)
def validate_letter_production_run_date(instance):
    if isinstance(instance, str):
        if re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+", instance):
            return True

    raise InvalidRecipientError(message="Datetime format is invalid. It must be in the format %Y-%m-%d %H:%M:%S.%f")


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
            "{} {}".format(e.path[0] if e.path else "", e.schema["validationMessage"]).strip()
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
        if e.cause:
            try:
                error_message = e.cause.get_v2_message()
            except AttributeError:
                error_message = str(e.cause)
        else:
            error_message = e.message
        return error_message.replace("'", "")

    path = get_path(e)
    message = get_error_message(e)
    if path:
        return f"{path} {message}"
    else:
        return f"{message}"
