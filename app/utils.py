import base64
from collections.abc import Callable, Generator, Iterable
from contextlib import suppress
from datetime import date, datetime, timedelta
from functools import wraps
from inspect import signature
from itertools import islice
from typing import Any, overload
from urllib.parse import urljoin
from uuid import UUID

from flask import current_app, url_for
from flask_sqlalchemy.pagination import Pagination
from notifications_utils.recipient_validation.errors import InvalidPhoneError
from notifications_utils.recipient_validation.phone_number import PhoneNumber, international_phone_info
from notifications_utils.s3 import S3ObjectNotFound
from notifications_utils.s3 import s3download as utils_s3download
from notifications_utils.template import (
    HTMLEmailTemplate,
    LetterPrintTemplate,
    SMSMessageTemplate,
    Template,
)
from notifications_utils.timezones import convert_bst_to_utc, utc_string_to_aware_gmt_datetime
from notifications_utils.url_safe_token import generate_token
from sqlalchemy import ColumnExpressionArgument, FunctionElement, func
from sqlalchemy.exc import OperationalError

from app.constants import (
    EMAIL_TYPE,
    LETTER_TYPE,
    SMS_TYPE,
    CacheKeys,
)

DATETIME_FORMAT_NO_TIMEZONE = "%Y-%m-%d %H:%M:%S.%f"
DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
DATE_FORMAT = "%Y-%m-%d"


def pagination_links(pagination: Pagination, endpoint: str, **kwargs) -> dict[str, str]:
    if "page" in kwargs:
        kwargs.pop("page", None)
    links = {}
    if pagination.has_prev:
        links["prev"] = url_for(endpoint, page=pagination.prev_num, **kwargs)
    if pagination.has_next:
        links["next"] = url_for(endpoint, page=pagination.next_num, **kwargs)
        links["last"] = url_for(endpoint, page=pagination.pages, **kwargs)
    return links


# Not sure those links ever get utilised beyond checking if they exist - changing the mocks to nonsense in admin
# didn't break any tests, and admin does its own page counting - so maybe a bit redundant code here?
def get_prev_next_pagination_links(
    current_page: int, next_page_exists: bool, endpoint: str, **kwargs
) -> dict[str, bool]:
    if "page" in kwargs:
        kwargs.pop("page", None)
    links = {}
    if current_page > 1:
        links["prev"] = True
    if next_page_exists:
        links["next"] = True
    return links


# "approximate equivalent" of itertools.batched from python 3.12's documentation. remove once we upgrade
# past python 3.12 and use itertools' version instead
def batched[A](iterable: Iterable[A], n: int, *, strict: bool = False) -> Generator[tuple[A, ...]]:
    # batched('ABCDEFG', 3) → ABC DEF G
    if n < 1:
        raise ValueError("n must be at least one")
    iterator = iter(iterable)
    while batch := tuple(islice(iterator, n)):
        if strict and len(batch) != n:
            raise ValueError("batched(): incomplete batch")
        yield batch


def url_with_token(data, url: str, base_url: str | None = None) -> str:
    token = generate_token(data, current_app.config["SECRET_KEY"], current_app.config["DANGEROUS_SALT"])
    base_url = (base_url or current_app.config["ADMIN_BASE_URL"]) + url
    return urljoin(base_url, token)


def get_template_instance(template: dict[str, Any], values: dict[str, Any]) -> Template:
    return {SMS_TYPE: SMSMessageTemplate, EMAIL_TYPE: HTMLEmailTemplate, LETTER_TYPE: LetterPrintTemplate}[
        template["template_type"]
    ](template, values)


def get_london_midnight_in_utc(date: date) -> datetime:
    """
    This function converts date to midnight as BST (British Standard Time) to UTC,
    the tzinfo is lastly removed from the datetime because the database stores the timestamps without timezone.
    :param date: the day to calculate the London midnight in UTC for
    :return: the datetime of London midnight in UTC, for example 2016-06-17 = 2016-06-16 23:00:00
    """
    return convert_bst_to_utc(datetime.combine(date, datetime.min.time()))


def get_midnight_for_day_before(date: date) -> datetime:
    day_before = date - timedelta(1)
    return get_london_midnight_in_utc(day_before)


def get_london_month_from_utc_column(column: ColumnExpressionArgument) -> FunctionElement[datetime]:
    """
    Where queries need to count notifications by month it needs to be
    the month in BST (British Summer Time).
    The database stores all timestamps as UTC without the timezone.
     - First set the timezone on created_at to UTC
     - then convert the timezone to BST (or Europe/London)
     - lastly truncate the datetime to month with which we can group
       queries
    """
    return func.date_trunc("month", func.timezone("Europe/London", func.timezone("UTC", column)))


def get_public_notify_type_text(notify_type: str, plural: bool = False) -> str:
    notify_type_text = notify_type
    if notify_type == SMS_TYPE:
        notify_type_text = "text message"

    return "{}{}".format(notify_type_text, "s" if plural else "")


def midnight_n_days_ago(number_of_days: int) -> datetime:
    """
    Returns midnight a number of days ago. Takes care of daylight savings etc.
    """
    return get_london_midnight_in_utc(datetime.utcnow() - timedelta(days=number_of_days))


def escape_special_characters(string: str) -> str:
    for special_character in ("\\", "_", "%", "/"):
        string = string.replace(special_character, rf"\{special_character}")
    return string


def email_address_is_nhs(email_address: str) -> bool:
    return email_address.lower().endswith(
        (
            "@nhs.uk",
            "@nhs.net",
            ".nhs.uk",
            ".nhs.net",
        )
    )


def get_archived_db_column_value(column) -> str:
    date_time = datetime.utcnow().strftime("%Y-%m-%d-%H:%M:%S")
    return f"_archived_{date_time}_{column}"


@overload
def get_dt_string_or_none(val: None) -> None: ...


@overload
def get_dt_string_or_none(val: datetime) -> str: ...


def get_dt_string_or_none(val: datetime | None) -> str | None:
    return val.strftime(DATETIME_FORMAT) if val else None


@overload
def get_uuid_string_or_none(val: None) -> None: ...


@overload
def get_uuid_string_or_none(val: UUID) -> str: ...


def get_uuid_string_or_none(val: UUID | None) -> str | None:
    return str(val) if val else None


def format_sequential_number(sequential_number: int) -> str:
    return format(sequential_number, "x").zfill(8)


def get_ft_billing_data_for_today_updated_at() -> str | None:
    from app import redis_store

    if updated_at_utc_isoformat := redis_store.get(CacheKeys.FT_BILLING_FOR_TODAY_UPDATED_AT_UTC_ISOFORMAT):
        return updated_at_utc_isoformat.decode()

    return None


def utc_string_to_bst_string(utc_string: str) -> str:
    return utc_string_to_aware_gmt_datetime(utc_string).strftime("%Y-%m-%d %H:%M:%S")


def dict_filter(data_obj: Any, keys: Iterable[str]) -> dict[str, Any]:
    return {key: getattr(data_obj, key, None) for key in keys}


def try_parse_and_format_phone_number(number: str, log_msg=None, with_country_code=True) -> str:
    try:
        return parse_and_format_phone_number(number, with_country_code=with_country_code)
    except InvalidPhoneError as e:
        current_app.logger.warning("%s: %s", log_msg, e)
        return number


def parse_and_format_phone_number(number: str, with_country_code=True) -> str:
    phone_number = PhoneNumber(number)
    if not with_country_code:
        return str(phone_number.number.national_number)
    return phone_number.get_normalised_format()


def get_international_phone_info(number: str) -> international_phone_info:
    phone_number = PhoneNumber(number)
    return phone_number.get_international_phone_info()


def is_classmethod(method, cls: type) -> bool:
    with suppress(AttributeError, KeyError):
        return isinstance(cls.__dict__[method.__name__], classmethod)
    return False


def retryable_query[**A, R](
    default_retry_attempts: int = 0,  # note dormant by default
    exception_cls: type[BaseException] = OperationalError,
) -> Callable[[Callable[A, R]], Callable[A, R]]:
    """
    Returns a decorator that will, if activated either through `default_retry_attempts` or
    the "direct" argument `retry_attempts` being non-zero, will catch exceptions of type
    `exception_cls` and re-run the function body following a session.rollback() (note
    therefore this can only wrap functions that have a `session` argument so we know what
    to roll back).

    Beware it is not always appropriate to quietly roll back a transaction, so this should
    only be "activated" in cases where this is ok - this is why it defaults to having no
    action.
    """

    def retry_decorator(inner: Callable[A, R]) -> Callable[A, R]:
        sig = signature(inner)
        if "session" not in sig.parameters:
            raise TypeError("retryable_query can only decorate functions with an argument named `session`")

        @wraps(inner)
        def retry_wrapper(*args, **kwargs):
            retry_attempts = kwargs.pop("retry_attempts", default_retry_attempts)

            for attempt in range(retry_attempts + 1):
                try:
                    return inner(*args, **kwargs)
                except exception_cls:
                    if attempt >= retry_attempts:
                        raise

                    extra = {"retry_number": attempt}  # type: dict[str, Any]
                    current_app.logger.warning(
                        "Attempt %(retry_number)s of query failed", extra, exc_info=True, extra=extra
                    )

                    # need to figure out what session we're supposed to be rolling back
                    bound_args = sig.bind(*args, **kwargs)
                    bound_args.apply_defaults()
                    session = bound_args.arguments["session"]

                    session.rollback()

        return retry_wrapper  # type: ignore  # Concatenate can't handle kwargs (yet?)

    return retry_decorator


def try_download_template_email_file_from_s3(service_id, template_email_file_id):
    file_path = f"{service_id}/{template_email_file_id}"
    try:
        file = base64.b64encode(
            utils_s3download(
                bucket_name=current_app.config["S3_BUCKET_TEMPLATE_EMAIL_FILES"], filename=file_path
            ).read()
        ).decode("utf-8")
        return file

    except S3ObjectNotFound as e:
        current_app.logger.warning(
            "Template email file %s not in %s bucket",
            template_email_file_id,
            current_app.config["S3_BUCKET_TEMPLATE_EMAIL_FILES"],
            extra={
                "service_id": service_id,
                "file_id": template_email_file_id,
                "s3_key": file_path,
                "s3_bucket": current_app.config["S3_BUCKET_TEMPLATE_EMAIL_FILES"],
            },
        )

        raise e
