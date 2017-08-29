from datetime import date, datetime, timedelta

from freezegun import freeze_time

from app.dao.notifications_dao import dao_get_total_notifications_sent_per_day_for_perfomance_platform
from app.models import KEY_TYPE_NORMAL, KEY_TYPE_TEAM, KEY_TYPE_TEST

from tests.app.db import create_notification


def test_get_total_notifications_filters_on_date(sample_template):
    create_notification(sample_template, created_at=datetime(2016, 10, 17, 10, 0))
    create_notification(sample_template, created_at=datetime(2016, 10, 18, 10, 0))
    create_notification(sample_template, created_at=datetime(2016, 10, 19, 10, 0))
    result = dao_get_total_notifications_sent_per_day_for_perfomance_platform(date(2016, 10, 18), date(2016, 10, 19))
    assert result.messages_total == 1


def test_get_total_notifications_filters_on_date_at_midnight(sample_template):
    create_notification(sample_template, created_at=datetime(2016, 10, 17, 23, 59, 59))
    create_notification(sample_template, created_at=datetime(2016, 10, 18, 0, 0))
    create_notification(sample_template, created_at=datetime(2016, 10, 18, 23, 59, 59))
    create_notification(sample_template, created_at=datetime(2016, 10, 19, 0, 0))
    result = dao_get_total_notifications_sent_per_day_for_perfomance_platform(date(2016, 10, 18), date(2016, 10, 19))
    assert result.messages_total == 2


@freeze_time('2016-10-18T10:00')
def test_get_total_notifications_only_counts_api_notifications(sample_template, sample_job, sample_api_key):
    create_notification(sample_template, one_off=True)
    create_notification(sample_template, one_off=True)
    create_notification(sample_template, job=sample_job)
    create_notification(sample_template, job=sample_job)
    create_notification(sample_template, api_key=sample_api_key)
    result = dao_get_total_notifications_sent_per_day_for_perfomance_platform(date(2016, 10, 18), date(2016, 10, 19))
    assert result.messages_total == 1


@freeze_time('2016-10-18T10:00')
def test_get_total_notifications_ignores_test_keys(sample_template):
    # Creating multiple templates with normal and team keys but only 1 template
    # with a test key to test that the count ignores letters
    create_notification(sample_template, key_type=KEY_TYPE_NORMAL)
    create_notification(sample_template, key_type=KEY_TYPE_NORMAL)
    create_notification(sample_template, key_type=KEY_TYPE_TEAM)
    create_notification(sample_template, key_type=KEY_TYPE_TEAM)
    create_notification(sample_template, key_type=KEY_TYPE_TEST)
    result = dao_get_total_notifications_sent_per_day_for_perfomance_platform(date(2016, 10, 18), date(2016, 10, 19))
    assert result.messages_total == 4


@freeze_time('2016-10-18T10:00')
def test_get_total_notifications_ignores_letters(
    sample_template,
    sample_email_template,
    sample_letter_template
):
    # Creating multiple sms and email templates but only 1 letter template to
    # test that the count ignores letters
    create_notification(sample_template)
    create_notification(sample_template)
    create_notification(sample_email_template)
    create_notification(sample_email_template)
    create_notification(sample_letter_template)
    result = dao_get_total_notifications_sent_per_day_for_perfomance_platform(date(2016, 10, 18), date(2016, 10, 19))
    assert result.messages_total == 4


@freeze_time('2016-10-18T10:00')
def test_get_total_notifications_counts_messages_within_10_seconds(sample_template):
    created_at = datetime.utcnow()

    create_notification(sample_template, sent_at=created_at + timedelta(seconds=5))
    create_notification(sample_template, sent_at=created_at + timedelta(seconds=10))
    create_notification(sample_template, sent_at=created_at + timedelta(seconds=15))

    result = dao_get_total_notifications_sent_per_day_for_perfomance_platform(date(2016, 10, 18), date(2016, 10, 19))
    assert result.messages_total == 3
    assert result.messages_within_10_secs == 2


@freeze_time('2016-10-18T10:00')
def test_get_total_notifications_counts_messages_that_have_not_sent(sample_template):
    create_notification(sample_template, status='created', sent_at=None)
    result = dao_get_total_notifications_sent_per_day_for_perfomance_platform(date(2016, 10, 18), date(2016, 10, 19))
    assert result.messages_total == 1
    assert result.messages_within_10_secs == 0
