import json
import uuid
from datetime import date, datetime

import pytest
from freezegun import freeze_time
from notifications_utils.url_safe_token import generate_token

from app.utils import (
    format_sequential_number,
    get_london_midnight_in_utc,
    get_midnight_for_day_before,
    midnight_n_days_ago,
    url_with_token,
)


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


def test_url_with_token__create_confirmation_url(sample_email_notification, hostnames, notify_api):
    data = json.dumps({"user_id": str(uuid.uuid4()), "email": "foo@bar.com"})
    base_url = hostnames.admin
    url = "/user-profile/email/confirm/"
    token = generate_token(str(data), notify_api.config["SECRET_KEY"], notify_api.config["DANGEROUS_SALT"])

    expected_unsubscribe_link = f"{base_url}/user-profile/email/confirm/{token}"
    generated_unsubscribe_link = url_with_token(data, url=url, base_url=base_url)

    assert generated_unsubscribe_link == expected_unsubscribe_link
