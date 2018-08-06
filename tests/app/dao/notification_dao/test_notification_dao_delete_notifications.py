from datetime import (
    datetime,
    date,
    timedelta
)
import pytest
from freezegun import freeze_time
from app.dao.notifications_dao import delete_notifications_created_more_than_a_week_ago_by_type
from app.models import Notification, NotificationHistory
from tests.app.db import (
    create_template,
    create_notification,
    create_service_data_retention,
    create_service
)


@pytest.mark.parametrize('month, delete_run_time',
                         [(4, '2016-04-10 23:40'), (1, '2016-01-11 00:40')])
@pytest.mark.parametrize(
    'notification_type, expected_sms_count, expected_email_count, expected_letter_count',
    [('sms', 7, 10, 10),
     ('email', 10, 7, 10),
     ('letter', 10, 10, 7)]
)
def test_should_delete_notifications_by_type_after_seven_days(
        sample_service,
        month,
        delete_run_time,
        notification_type,
        expected_sms_count,
        expected_email_count,
        expected_letter_count
):
    assert len(Notification.query.all()) == 0
    email_template, letter_template, sms_template = _create_templates(sample_service)
    # create one notification a day between 1st and 10th from 11:00 to 19:00 of each type
    for i in range(1, 11):
        past_date = '2016-0{0}-{1:02d}  {1:02d}:00:00.000000'.format(month, i)
        with freeze_time(past_date):
            create_notification(template=email_template, created_at=datetime.utcnow(), status="permanent-failure")
            create_notification(template=sms_template, created_at=datetime.utcnow(), status="delivered")
            create_notification(template=letter_template, created_at=datetime.utcnow(), status="temporary-failure")
    all_notifications = Notification.query.all()
    assert len(all_notifications) == 30
    # Records from before 3rd should be deleted
    with freeze_time(delete_run_time):
        delete_notifications_created_more_than_a_week_ago_by_type(notification_type)
    remaining_sms_notifications = Notification.query.filter_by(notification_type='sms').all()
    remaining_letter_notifications = Notification.query.filter_by(notification_type='letter').all()
    remaining_email_notifications = Notification.query.filter_by(notification_type='email').all()
    assert len(remaining_sms_notifications) == expected_sms_count
    assert len(remaining_email_notifications) == expected_email_count
    assert len(remaining_letter_notifications) == expected_letter_count

    if notification_type == 'sms':
        notifications_to_check = remaining_sms_notifications
    if notification_type == 'email':
        notifications_to_check = remaining_email_notifications
    if notification_type == 'letter':
        notifications_to_check = remaining_letter_notifications
    for notification in notifications_to_check:
        assert notification.created_at.date() >= date(2016, month, 3)


@pytest.mark.parametrize('notification_type', ['sms', 'email', 'letter'])
@freeze_time("2016-01-10 12:00:00.000000")
def test_should_not_delete_notification_history(sample_service, notification_type):
    with freeze_time('2016-01-01 12:00'):
        email_template, letter_template, sms_template = _create_templates(sample_service)
        create_notification(template=email_template, status='permanent-failure')
        create_notification(template=sms_template, status='permanent-failure')
        create_notification(template=letter_template, status='permanent-failure')
    assert Notification.query.count() == 3
    assert NotificationHistory.query.count() == 3
    delete_notifications_created_more_than_a_week_ago_by_type(notification_type)
    assert Notification.query.count() == 2
    assert NotificationHistory.query.count() == 3


@pytest.mark.parametrize('notification_type', ['sms', 'email', 'letter'])
def test_delete_notifications_for_days_of_retention(sample_service, notification_type):
    service_with_default_data_retention = create_service(service_name='default data retention')
    email_template, letter_template, sms_template = _create_templates(sample_service)
    default_email_template, default_letter_template, default_sms_template = _create_templates(
        service_with_default_data_retention)
    create_notification(template=email_template, status='delivered')
    create_notification(template=sms_template, status='permanent-failure')
    create_notification(template=letter_template, status='temporary-failure')
    create_notification(template=email_template, status='delivered',
                        created_at=datetime.utcnow() - timedelta(days=4))
    create_notification(template=sms_template, status='permanent-failure',
                        created_at=datetime.utcnow() - timedelta(days=4))
    create_notification(template=letter_template, status='temporary-failure',
                        created_at=datetime.utcnow() - timedelta(days=4))
    create_notification(template=default_email_template, status='delivered',
                        created_at=datetime.utcnow() - timedelta(days=8))
    create_notification(template=default_sms_template, status='permanent-failure',
                        created_at=datetime.utcnow() - timedelta(days=8))
    create_notification(template=default_letter_template, status='temporary-failure',
                        created_at=datetime.utcnow() - timedelta(days=8))
    create_service_data_retention(service_id=sample_service.id, notification_type=notification_type)
    assert len(Notification.query.all()) == 9
    delete_notifications_created_more_than_a_week_ago_by_type(notification_type)
    assert len(Notification.query.all()) == 7
    assert len(Notification.query.filter_by(notification_type=notification_type).all()) == 1


@pytest.mark.parametrize('notification_type', ['sms', 'email', 'letter'])
def test_delete_notifications_keep_data_for_days_of_retention_is_longer(sample_service, notification_type):
    create_service_data_retention(service_id=sample_service.id, notification_type=notification_type,
                                  days_of_retention=15)
    email_template, letter_template, sms_template = _create_templates(sample_service)
    service_with_default_data_retention = create_service(service_name='default data retention')
    default_email_template, default_letter_template, default_sms_template = _create_templates(
        service_with_default_data_retention)
    create_notification(template=email_template, status='delivered')
    create_notification(template=sms_template, status='permanent-failure')
    create_notification(template=letter_template, status='temporary-failure')
    create_notification(template=email_template, status='delivered',
                        created_at=datetime.utcnow() - timedelta(days=14))
    create_notification(template=sms_template, status='permanent-failure',
                        created_at=datetime.utcnow() - timedelta(days=14))
    create_notification(template=letter_template, status='temporary-failure',
                        created_at=datetime.utcnow() - timedelta(days=14))
    create_notification(template=default_email_template, status='delivered',
                        created_at=datetime.utcnow() - timedelta(days=8))
    create_notification(template=default_sms_template, status='permanent-failure',
                        created_at=datetime.utcnow() - timedelta(days=8))
    create_notification(template=default_letter_template, status='temporary-failure',
                        created_at=datetime.utcnow() - timedelta(days=8))
    assert len(Notification.query.all()) == 9
    delete_notifications_created_more_than_a_week_ago_by_type(notification_type)
    assert len(Notification.query.filter_by().all()) == 8
    assert len(Notification.query.filter_by(notification_type=notification_type).all()) == 2


def test_delete_notifications_delete_notification_type_for_default_time_if_no_days_of_retention_for_type(
        sample_service
):
    create_service_data_retention(service_id=sample_service.id, notification_type='sms',
                                  days_of_retention=15)
    email_template, letter_template, sms_template = _create_templates(sample_service)
    create_notification(template=email_template, status='delivered')
    create_notification(template=sms_template, status='permanent-failure')
    create_notification(template=letter_template, status='temporary-failure')
    create_notification(template=email_template, status='delivered',
                        created_at=datetime.utcnow() - timedelta(days=14))
    create_notification(template=sms_template, status='permanent-failure',
                        created_at=datetime.utcnow() - timedelta(days=14))
    create_notification(template=letter_template, status='temporary-failure',
                        created_at=datetime.utcnow() - timedelta(days=14))
    assert len(Notification.query.all()) == 6
    delete_notifications_created_more_than_a_week_ago_by_type('email')
    assert len(Notification.query.filter_by().all()) == 5
    assert len(Notification.query.filter_by(notification_type='email').all()) == 1


def _create_templates(sample_service):
    email_template = create_template(service=sample_service, template_type='email')
    sms_template = create_template(service=sample_service)
    letter_template = create_template(service=sample_service, template_type='letter')
    return email_template, letter_template, sms_template
