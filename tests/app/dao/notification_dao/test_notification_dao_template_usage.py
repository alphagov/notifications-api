import uuid
from datetime import datetime, timedelta, date

import pytest
from freezegun import freeze_time

from app.dao.notifications_dao import (
    dao_get_last_template_usage,
    dao_get_template_usage
)
from app.models import (
    KEY_TYPE_NORMAL,
    KEY_TYPE_TEST,
    KEY_TYPE_TEAM
)
from tests.app.db import (
    create_notification,
    create_service,
    create_template
)


def test_last_template_usage_should_get_right_data(sample_notification):
    results = dao_get_last_template_usage(sample_notification.template_id, 'sms')
    assert results.template.name == 'Template Name'
    assert results.template.template_type == 'sms'
    assert results.created_at == sample_notification.created_at
    assert results.template_id == sample_notification.template_id
    assert results.id == sample_notification.id


@pytest.mark.parametrize('notification_type', ['sms', 'email', 'letter'])
def test_last_template_usage_should_be_able_to_get_all_template_usage_history_order_by_notification_created_at(
        sample_service,
        notification_type
):
    template = create_template(sample_service, template_type=notification_type)

    create_notification(template)
    create_notification(template)
    create_notification(template)
    most_recent = create_notification(template)

    results = dao_get_last_template_usage(template.id, notification_type)
    assert results.id == most_recent.id


def test_last_template_usage_should_ignore_test_keys(
        sample_template,
        sample_team_api_key,
        sample_test_api_key
):
    one_minute_ago = datetime.utcnow() - timedelta(minutes=1)
    two_minutes_ago = datetime.utcnow() - timedelta(minutes=2)

    team_key = create_notification(
        template=sample_template,
        created_at=two_minutes_ago,
        api_key=sample_team_api_key)
    create_notification(
        template=sample_template,
        created_at=one_minute_ago,
        api_key=sample_test_api_key)

    results = dao_get_last_template_usage(sample_template.id, 'sms')
    assert results.id == team_key.id


def test_last_template_usage_should_be_able_to_get_no_template_usage_history_if_no_notifications_using_template(
        sample_template):
    results = dao_get_last_template_usage(sample_template.id, 'sms')
    assert not results


def test_should_by_able_to_get_template_count(sample_template, sample_email_template):
    create_notification(sample_template)
    create_notification(sample_template)
    create_notification(sample_template)
    create_notification(sample_email_template)
    create_notification(sample_email_template)

    results = dao_get_template_usage(sample_template.service_id, limit_days=1)
    assert results[0].name == 'Email Template Name'
    assert results[0].template_type == 'email'
    assert results[0].count == 2

    assert results[1].name == 'Template Name'
    assert results[1].template_type == 'sms'
    assert results[1].count == 3


def test_template_usage_should_ignore_test_keys(
    sample_team_api_key,
    sample_test_api_key,
    sample_api_key,
    sample_template
):

    create_notification(sample_template, api_key=sample_api_key, key_type=KEY_TYPE_NORMAL)
    create_notification(sample_template, api_key=sample_team_api_key, key_type=KEY_TYPE_TEAM)
    create_notification(sample_template, api_key=sample_test_api_key, key_type=KEY_TYPE_TEST)
    create_notification(sample_template)

    results = dao_get_template_usage(sample_template.service_id, limit_days=1)
    assert results[0].name == 'Template Name'
    assert results[0].template_type == 'sms'
    assert results[0].count == 3


def test_template_usage_should_filter_by_service(notify_db_session):
    service_1 = create_service(service_name='test1')
    service_2 = create_service(service_name='test2')
    service_3 = create_service(service_name='test3')

    template_1 = create_template(service_1)
    template_2 = create_template(service_2)  # noqa
    template_3a = create_template(service_3)
    template_3b = create_template(service_3)  # noqa

    # two for service_1, one for service_3
    create_notification(template_1)
    create_notification(template_1)

    create_notification(template_3a)

    res1 = dao_get_template_usage(service_1.id, limit_days=1)
    res2 = dao_get_template_usage(service_2.id, limit_days=1)
    res3 = dao_get_template_usage(service_3.id, limit_days=1)

    assert len(res1) == 1
    assert res1[0].count == 2

    assert len(res2) == 1
    assert res2[0].count == 0

    assert len(res3) == 2
    assert res3[0].count == 1
    assert res3[1].count == 0


def test_template_usage_should_by_able_to_get_zero_count_from_notifications_history_if_no_rows(sample_service):
    results = dao_get_template_usage(sample_service.id, limit_days=1)
    assert len(results) == 0


def test_template_usage_should_by_able_to_get_zero_count_from_notifications_history_if_no_service():
    results = dao_get_template_usage(str(uuid.uuid4()), limit_days=1)
    assert len(results) == 0


@freeze_time('2017-06-10T12:00:00')
def test_template_usage_should_by_able_to_get_template_count_with_limit_days(sample_template):
    # too early
    create_notification(sample_template, created_at=datetime(2017, 6, 7, 22, 59, 0))
    # just right
    create_notification(sample_template, created_at=datetime(2017, 6, 7, 23, 0, 0))
    create_notification(sample_template, created_at=datetime(2017, 6, 7, 23, 0, 0))
    create_notification(sample_template, created_at=datetime(2017, 6, 8, 22, 59, 0))
    create_notification(sample_template, created_at=datetime(2017, 6, 8, 22, 59, 0))
    create_notification(sample_template, created_at=datetime(2017, 6, 8, 22, 59, 0))
    # next day, still included
    create_notification(sample_template, created_at=datetime(2017, 6, 8, 23, 0, 0))

    results = dao_get_template_usage(sample_template.service_id, limit_days=2)

    assert len(results) == 1
    assert results[0].count == 6


@freeze_time('2017-06-10T12:00:00')
def test_template_usage_should_by_able_to_get_template_count_for_specific_day(sample_template):
    # too early
    create_notification(sample_template, created_at=datetime(2017, 6, 7, 22, 59, 0))
    # just right
    create_notification(sample_template, created_at=datetime(2017, 6, 7, 23, 0, 0))
    create_notification(sample_template, created_at=datetime(2017, 6, 7, 23, 0, 0))
    create_notification(sample_template, created_at=datetime(2017, 6, 8, 22, 59, 0))
    create_notification(sample_template, created_at=datetime(2017, 6, 8, 22, 59, 0))
    create_notification(sample_template, created_at=datetime(2017, 6, 8, 22, 59, 0))
    # too late
    create_notification(sample_template, created_at=datetime(2017, 6, 8, 23, 0, 0))

    results = dao_get_template_usage(sample_template.service_id, day=date(2017, 6, 8))

    assert len(results) == 1
    assert results[0].count == 5


@pytest.mark.parametrize('kwargs', [
    {},
    {'limit_days': 0},
    {'limit_days': 1, 'day': date(2017, 1, 1)}
])
def test_template_usage_rejects_invalid_params(kwargs):
    with pytest.raises(ValueError):
        dao_get_template_usage(uuid.uuid4(), **kwargs)
