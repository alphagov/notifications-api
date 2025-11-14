import json
import uuid
from datetime import date, datetime

import pytest
from flask import current_app
from freezegun import freeze_time
from notifications_utils.s3 import S3ObjectNotFound
from notifications_utils.url_safe_token import generate_token

from app.constants import EMAIL_TYPE
from app.serialised_models import SerialisedTemplate
from app.utils import (
    EmailFilePlaceholder,
    extract_email_file_placeholders,
    format_sequential_number,
    get_london_midnight_in_utc,
    get_midnight_for_day_before,
    midnight_n_days_ago,
    try_download_template_email_file_from_s3,
    url_with_token,
)
from app.v2.errors import BadRequestError
from tests.app.db import create_template


@pytest.mark.parametrize(
    "date, expected_date",
    [
        (datetime(2016, 1, 15, 0, 30), datetime(2016, 1, 15, 0, 0)),
        (datetime(2016, 6, 15, 0, 0), datetime(2016, 6, 14, 23, 0)),
        (datetime(2016, 9, 15, 11, 59), datetime(2016, 9, 14, 23, 0)),
        # works for both dates and datetimes
        (date(2016, 1, 15), datetime(2016, 1, 15, 0, 0)),
        (date(2016, 6, 15), datetime(2016, 6, 14, 23, 0)),
    ],
)
def test_get_london_midnight_in_utc_returns_expected_date(date, expected_date):
    assert get_london_midnight_in_utc(date) == expected_date


@pytest.mark.parametrize(
    "date, expected_date",
    [
        (datetime(2016, 1, 15, 0, 30), datetime(2016, 1, 14, 0, 0)),
        (datetime(2016, 7, 15, 0, 0), datetime(2016, 7, 13, 23, 0)),
        (datetime(2016, 8, 23, 11, 59), datetime(2016, 8, 21, 23, 0)),
    ],
)
def test_get_midnight_for_day_before_returns_expected_date(date, expected_date):
    assert get_midnight_for_day_before(date) == expected_date


@pytest.mark.parametrize(
    "current_time, arg, expected_datetime",
    [
        # winter
        ("2018-01-10 23:59", 1, datetime(2018, 1, 9, 0, 0)),
        ("2018-01-11 00:00", 1, datetime(2018, 1, 10, 0, 0)),
        # bst switchover at 1am 25th
        ("2018-03-25 10:00", 1, datetime(2018, 3, 24, 0, 0)),
        ("2018-03-26 10:00", 1, datetime(2018, 3, 25, 0, 0)),
        ("2018-03-27 10:00", 1, datetime(2018, 3, 25, 23, 0)),
        # summer
        ("2018-06-05 10:00", 1, datetime(2018, 6, 3, 23, 0)),
        # zero days ago
        ("2018-01-11 00:00", 0, datetime(2018, 1, 11, 0, 0)),
        ("2018-06-05 10:00", 0, datetime(2018, 6, 4, 23, 0)),
    ],
)
def test_midnight_n_days_ago(current_time, arg, expected_datetime):
    with freeze_time(current_time):
        assert midnight_n_days_ago(arg) == expected_datetime


def test_format_sequential_number():
    assert format_sequential_number(123) == "0000007b"


def test_url_with_token_unsubscribe_link(sample_email_notification, hostnames, notify_api):
    data = str(sample_email_notification.to)
    notification_id = sample_email_notification.id
    base_url = hostnames.api
    url = f"/unsubscribe/{str(notification_id)}/"
    token = generate_token(data, notify_api.config["SECRET_KEY"], notify_api.config["DANGEROUS_SALT"])

    expected_unsubscribe_link = f"{base_url}/unsubscribe/{notification_id}/{token}"
    generated_unsubscribe_link = url_with_token(data, url=url, base_url=base_url)

    assert generated_unsubscribe_link == expected_unsubscribe_link


def test_url_with_token__create_confirmation_url(hostnames, notify_api):
    data = json.dumps({"user_id": str(uuid.uuid4()), "email": "foo@bar.com"})
    base_url = hostnames.admin
    url = "/your-account/email/confirm/"
    token = generate_token(str(data), notify_api.config["SECRET_KEY"], notify_api.config["DANGEROUS_SALT"])

    expected_unsubscribe_link = f"{base_url}/your-account/email/confirm/{token}"
    generated_unsubscribe_link = url_with_token(data, url=url, base_url=base_url)

    assert generated_unsubscribe_link == expected_unsubscribe_link


def test_EmailFilePlaceholder_happy_path():
    email_file_placeholder = EmailFilePlaceholder("file::invitation.pdf::36fb0730-6259-4da1-8a80-c8de22ad4246")
    assert email_file_placeholder.string == "file::invitation.pdf::36fb0730-6259-4da1-8a80-c8de22ad4246"
    assert email_file_placeholder.id == "36fb0730-6259-4da1-8a80-c8de22ad4246"


def test_EmailFilePlaceholder_invalid_uuid():
    with pytest.raises(BadRequestError) as e:
        EmailFilePlaceholder("file::invitation.pdf::blah")

    assert e.value.status_code == 400
    assert e.value.message == "template_email_file_id blah is not a valid UUID."


def test_extract_email_file_placeholders(notify_api, mocker, sample_service):
    content = """
    Dear ((name)),

    Here is your invitation:
    ((file::invitation.pdf::36fb0730-6259-4da1-8a80-c8de22ad4246))

    And here is the form to bring to the appointment:
    ((file::form.pdf::429c0b16-704e-41cb-8181-6448567f7042))
    """
    template_id = create_template(sample_service, content=content, template_type=EMAIL_TYPE).id
    template = SerialisedTemplate.from_id_and_service_id(template_id=template_id, service_id=sample_service.id)
    email_files = extract_email_file_placeholders(template)

    assert email_files[0].string == "file::invitation.pdf::36fb0730-6259-4da1-8a80-c8de22ad4246"

    assert email_files[1].string == "file::form.pdf::429c0b16-704e-41cb-8181-6448567f7042"


def test_extract_email_file_placeholders_when_none_found(notify_api, mocker, sample_service):
    content = """
    Dear ((name)),

    Your verification code is: 123 456
    """
    template_id = create_template(sample_service, content=content, template_type=EMAIL_TYPE).id
    template = SerialisedTemplate.from_id_and_service_id(template_id=template_id, service_id=sample_service.id)
    assert extract_email_file_placeholders(template) == []


def test_try_download_template_email_file_from_s3(mocker, sample_service, fake_uuid):
    mock_utils_s3download = mocker.patch("app.utils.utils_s3download")

    try_download_template_email_file_from_s3(service_id=sample_service.id, template_email_file_id=fake_uuid)
    mock_utils_s3download.assert_called_once_with(
        bucket_name=current_app.config["S3_BUCKET_TEMPLATE_EMAIL_FILES"],
        filename=f"{sample_service.id}/{fake_uuid}",
    )


def test_try_download_template_email_file_from_s3_raises_error_when_file_not_in_bucket(
    mocker, sample_service, fake_uuid
):
    mocker.patch(
        "app.utils.utils_s3download",
        side_effect=S3ObjectNotFound({}, ""),
    )

    with pytest.raises(S3ObjectNotFound):
        try_download_template_email_file_from_s3(service_id=sample_service.id, template_email_file_id=fake_uuid)
