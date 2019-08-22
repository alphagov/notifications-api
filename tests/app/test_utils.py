from datetime import datetime, date

import pytest
from freezegun import freeze_time

from app.utils import (
    get_london_midnight_in_utc,
    get_midnight_for_day_before,
    midnight_n_days_ago,
    get_notification_table_to_use,
)
from app.models import Notification, NotificationHistory

from tests.app.db import create_service_data_retention


@pytest.mark.parametrize('date, expected_date', [
    (datetime(2016, 1, 15, 0, 30), datetime(2016, 1, 15, 0, 0)),
    (datetime(2016, 6, 15, 0, 0), datetime(2016, 6, 14, 23, 0)),
    (datetime(2016, 9, 15, 11, 59), datetime(2016, 9, 14, 23, 0)),
    # works for both dates and datetimes
    (date(2016, 1, 15), datetime(2016, 1, 15, 0, 0)),
    (date(2016, 6, 15), datetime(2016, 6, 14, 23, 0)),
])
def test_get_london_midnight_in_utc_returns_expected_date(date, expected_date):
    assert get_london_midnight_in_utc(date) == expected_date


@pytest.mark.parametrize('date, expected_date', [
    (datetime(2016, 1, 15, 0, 30), datetime(2016, 1, 14, 0, 0)),
    (datetime(2016, 7, 15, 0, 0), datetime(2016, 7, 13, 23, 0)),
    (datetime(2016, 8, 23, 11, 59), datetime(2016, 8, 21, 23, 0)),
])
def test_get_midnight_for_day_before_returns_expected_date(date, expected_date):
    assert get_midnight_for_day_before(date) == expected_date


@pytest.mark.parametrize('current_time, arg, expected_datetime', [
    # winter
    ('2018-01-10 23:59', 1, datetime(2018, 1, 9, 0, 0)),
    ('2018-01-11 00:00', 1, datetime(2018, 1, 10, 0, 0)),

    # bst switchover at 1am 25th
    ('2018-03-25 10:00', 1, datetime(2018, 3, 24, 0, 0)),
    ('2018-03-26 10:00', 1, datetime(2018, 3, 25, 0, 0)),
    ('2018-03-27 10:00', 1, datetime(2018, 3, 25, 23, 0)),

    # summer
    ('2018-06-05 10:00', 1, datetime(2018, 6, 3, 23, 0)),

    # zero days ago
    ('2018-01-11 00:00', 0, datetime(2018, 1, 11, 0, 0)),
    ('2018-06-05 10:00', 0, datetime(2018, 6, 4, 23, 0)),
])
def test_midnight_n_days_ago(current_time, arg, expected_datetime):
    with freeze_time(current_time):
        assert midnight_n_days_ago(arg) == expected_datetime


@freeze_time('2019-01-10 00:30')
def test_get_notification_table_to_use(sample_service):
    # it's currently early morning of Thurs 10th Jan.
    # When the delete task runs a bit later, it'll delete data from last wednesday 2nd.
    assert get_notification_table_to_use(sample_service, 'sms', date(2018, 12, 31), False) == NotificationHistory
    assert get_notification_table_to_use(sample_service, 'sms', date(2019, 1, 1), False) == NotificationHistory
    assert get_notification_table_to_use(sample_service, 'sms', date(2019, 1, 2), False) == Notification
    assert get_notification_table_to_use(sample_service, 'sms', date(2019, 1, 3), False) == Notification


@freeze_time('2019-01-10 00:30')
def test_get_notification_table_to_use_knows_if_delete_task_has_run(sample_service):
    # it's currently early morning of Thurs 10th Jan.
    # The delete task deletes/moves data from last wednesday 2nd.
    assert get_notification_table_to_use(sample_service, 'sms', date(2019, 1, 2), False) == Notification
    assert get_notification_table_to_use(sample_service, 'sms', date(2019, 1, 2), True) == NotificationHistory


@freeze_time('2019-06-09 23:30')
def test_get_notification_table_to_use_respects_daylight_savings_time(sample_service):
    # current time is 12:30am on 10th july in BST
    assert get_notification_table_to_use(sample_service, 'sms', date(2019, 6, 1), False) == NotificationHistory
    assert get_notification_table_to_use(sample_service, 'sms', date(2019, 6, 2), False) == Notification


@freeze_time('2019-01-10 00:30')
def test_get_notification_table_to_use_checks_service_data_retention(sample_service):
    create_service_data_retention(sample_service, 'email', days_of_retention=3)

    # it's currently early morning of Thurs 10th Jan.
    # three days retention means we'll delete sunday 6th's data when the delete task runs (so there's still three full
    # days of monday, tuesday and wednesday left over)
    assert get_notification_table_to_use(sample_service, 'email', date(2019, 1, 5), False) == NotificationHistory
    assert get_notification_table_to_use(sample_service, 'email', date(2019, 1, 6), False) == Notification

    # falls back to 7 days if not specified
    assert get_notification_table_to_use(sample_service, 'sms', date(2019, 1, 1), False) == NotificationHistory
    assert get_notification_table_to_use(sample_service, 'sms', date(2019, 1, 2), False) == Notification
