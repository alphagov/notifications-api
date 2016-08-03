from datetime import datetime
import uuid

import pytest

from app.models import NotificationHistory, KEY_TYPE_NORMAL, KEY_TYPE_TEAM, KEY_TYPE_TEST, NOTIFICATION_STATUS_TYPES
from app.dao.notifications_dao import update_provider_stats
from app.dao.provider_statistics_dao import get_provider_statistics, get_fragment_count
from tests.app.conftest import sample_notification as create_sample_notification


def test_should_update_provider_statistics_sms(notify_db,
                                               notify_db_session,
                                               sample_template,
                                               mmg_provider):
    n1 = create_sample_notification(
        notify_db,
        notify_db_session,
        template=sample_template)
    update_provider_stats(n1.id, 'sms', mmg_provider.identifier)
    provider_stats = get_provider_statistics(
        sample_template.service,
        providers=[mmg_provider.identifier]).one()
    assert provider_stats.unit_count == 1


def test_should_update_provider_statistics_email(notify_db,
                                                 notify_db_session,
                                                 sample_email_template,
                                                 ses_provider):
    n1 = create_sample_notification(
        notify_db,
        notify_db_session,
        template=sample_email_template)
    update_provider_stats(n1.id, 'email', ses_provider.identifier)
    provider_stats = get_provider_statistics(
        sample_email_template.service,
        providers=[ses_provider.identifier]).one()
    assert provider_stats.unit_count == 1


def test_should_update_provider_statistics_sms_multi(notify_db,
                                                     notify_db_session,
                                                     sample_template,
                                                     mmg_provider):
    n1 = create_sample_notification(
        notify_db,
        notify_db_session,
        template=sample_template,
        billable_units=1)
    update_provider_stats(n1.id, 'sms', mmg_provider.identifier, n1.billable_units)
    n2 = create_sample_notification(
        notify_db,
        notify_db_session,
        template=sample_template,
        billable_units=2)
    update_provider_stats(n2.id, 'sms', mmg_provider.identifier, n2.billable_units)
    n3 = create_sample_notification(
        notify_db,
        notify_db_session,
        template=sample_template,
        billable_units=4)
    update_provider_stats(n3.id, 'sms', mmg_provider.identifier, n3.billable_units)
    provider_stats = get_provider_statistics(
        sample_template.service,
        providers=[mmg_provider.identifier]).one()
    assert provider_stats.unit_count == 7


def test_should_update_provider_statistics_email_multi(notify_db,
                                                       notify_db_session,
                                                       sample_email_template,
                                                       ses_provider):
    n1 = create_sample_notification(
        notify_db,
        notify_db_session,
        template=sample_email_template)
    update_provider_stats(n1.id, 'email', ses_provider.identifier)
    n2 = create_sample_notification(
        notify_db,
        notify_db_session,
        template=sample_email_template)
    update_provider_stats(n2.id, 'email', ses_provider.identifier)
    n3 = create_sample_notification(
        notify_db,
        notify_db_session,
        template=sample_email_template)
    update_provider_stats(n3.id, 'email', ses_provider.identifier)
    provider_stats = get_provider_statistics(
        sample_email_template.service,
        providers=[ses_provider.identifier]).one()
    assert provider_stats.unit_count == 3


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
