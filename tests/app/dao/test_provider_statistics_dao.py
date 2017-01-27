from datetime import datetime
import uuid

import pytest
from freezegun import freeze_time

from app.models import NotificationHistory, KEY_TYPE_NORMAL, KEY_TYPE_TEAM, KEY_TYPE_TEST, NOTIFICATION_STATUS_TYPES
from app.dao.provider_statistics_dao import get_fragment_count


def test_get_fragment_count_with_no_data(sample_template):
    assert get_fragment_count(sample_template.service_id)['sms_count'] == 0
    assert get_fragment_count(sample_template.service_id)['email_count'] == 0


def test_get_fragment_count_separates_sms_and_email(notify_db, sample_template, sample_email_template):
    noti_hist(notify_db, sample_template)
    noti_hist(notify_db, sample_template)
    noti_hist(notify_db, sample_email_template)
    assert get_fragment_count(sample_template.service_id) == {
        'sms_count': 2,
        'email_count': 1
    }


def test_get_fragment_count_filters_on_status(notify_db, sample_template):
    for status in NOTIFICATION_STATUS_TYPES:
        noti_hist(notify_db, sample_template, status=status)
    # sending, delivered, failed, technical-failure, temporary-failure, permanent-failure
    assert get_fragment_count(sample_template.service_id)['sms_count'] == 6


def test_get_fragment_count_filters_on_service_id(notify_db, sample_template, service_factory):
    service_2 = service_factory.get('service 2', email_from='service.2')
    noti_hist(notify_db, sample_template)
    assert get_fragment_count(service_2.id)['sms_count'] == 0


@pytest.mark.parametrize('creation_time, expected_count', [
    ('2000-03-31 22:59:59', 0),  # before the start of the year
    ('2000-04-01 00:00:00', 1),  # after the start of the year
    ('2001-03-31 22:59:59', 1),  # before the end of the year
    ('2001-04-01 00:00:00', 0),  # after the end of the year
])
def test_get_fragment_count_filters_on_year(
    notify_db, sample_template, creation_time, expected_count
):
    with freeze_time(creation_time):
        noti_hist(notify_db, sample_template)
    assert get_fragment_count(sample_template.service_id, year=2000)['sms_count'] == expected_count


def test_get_fragment_count_sums_billable_units_for_sms(notify_db, sample_template):
    noti_hist(notify_db, sample_template, billable_units=1)
    noti_hist(notify_db, sample_template, billable_units=2)
    assert get_fragment_count(sample_template.service_id)['sms_count'] == 3


@pytest.mark.parametrize('key_type,sms_count', [
    (KEY_TYPE_NORMAL, 1),
    (KEY_TYPE_TEAM, 1),
    (KEY_TYPE_TEST, 0),
])
def test_get_fragment_count_ignores_test_api_keys(notify_db, sample_template, key_type, sms_count):
    noti_hist(notify_db, sample_template, key_type=key_type)
    assert get_fragment_count(sample_template.service_id)['sms_count'] == sms_count


def noti_hist(notify_db, template, status='delivered', billable_units=None, key_type=KEY_TYPE_NORMAL):
    if not billable_units and template.template_type == 'sms':
        billable_units = 1

    notification_history = NotificationHistory(
        id=uuid.uuid4(),
        service=template.service,
        template=template,
        template_version=template.version,
        status=status,
        created_at=datetime.utcnow(),
        billable_units=billable_units,
        notification_type=template.template_type,
        key_type=key_type
    )
    notify_db.session.add(notification_history)
    notify_db.session.commit()

    return notification_history
