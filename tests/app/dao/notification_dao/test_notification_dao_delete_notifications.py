from datetime import (
    datetime,
    date,
    timedelta
)
import pytest
from flask import current_app
from freezegun import freeze_time

from app.dao.notifications_dao import (
    delete_notifications_older_than_retention_by_type,
    insert_notification_history_delete_notifications
)
from app.models import Notification, NotificationHistory
from tests.app.db import (
    create_template,
    create_notification,
    create_service_data_retention,
    create_service,
    create_notification_history)


def create_test_data(notification_type, sample_service, days_of_retention=3):
    service_with_default_data_retention = create_service(service_name='default data retention')
    email_template, letter_template, sms_template = _create_templates(sample_service)
    default_email_template, default_letter_template, default_sms_template = _create_templates(
        service_with_default_data_retention)
    create_notification(template=email_template, status='delivered')
    create_notification(template=sms_template, status='permanent-failure')
    create_notification(template=letter_template, status='temporary-failure',
                        reference='LETTER_REF', created_at=datetime.utcnow(), sent_at=datetime.utcnow())
    create_notification(template=email_template, status='delivered',
                        created_at=datetime.utcnow() - timedelta(days=4))
    create_notification(template=sms_template, status='permanent-failure',
                        created_at=datetime.utcnow() - timedelta(days=4))
    create_notification(template=letter_template, status='temporary-failure',
                        reference='LETTER_REF', sent_at=datetime.utcnow(),
                        created_at=datetime.utcnow() - timedelta(days=4))
    create_notification(template=default_email_template, status='delivered',
                        created_at=datetime.utcnow() - timedelta(days=8))
    create_notification(template=default_sms_template, status='permanent-failure',
                        created_at=datetime.utcnow() - timedelta(days=8))
    create_notification(template=default_letter_template, status='temporary-failure',
                        reference='LETTER_REF', sent_at=datetime.utcnow(),
                        created_at=datetime.utcnow() - timedelta(days=8))
    create_service_data_retention(service=sample_service, notification_type=notification_type,
                                  days_of_retention=days_of_retention)


def _create_templates(sample_service):
    email_template = create_template(service=sample_service, template_type='email')
    sms_template = create_template(service=sample_service)
    letter_template = create_template(service=sample_service, template_type='letter')
    return email_template, letter_template, sms_template


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
        mocker,
        month,
        delete_run_time,
        notification_type,
        expected_sms_count,
        expected_email_count,
        expected_letter_count
):
    mocker.patch("app.dao.notifications_dao.get_s3_bucket_objects")
    email_template, letter_template, sms_template = _create_templates(sample_service)
    # create one notification a day between 1st and 10th from 11:00 to 19:00 of each type
    for i in range(1, 11):
        past_date = '2016-0{0}-{1:02d}  {1:02d}:00:00.000000'.format(month, i)
        with freeze_time(past_date):
            create_notification(template=email_template, created_at=datetime.utcnow(), status="permanent-failure")
            create_notification(template=sms_template, created_at=datetime.utcnow(), status="delivered")
            create_notification(template=letter_template, created_at=datetime.utcnow(), status="temporary-failure")
    assert Notification.query.count() == 30

    # Records from before 3rd should be deleted
    with freeze_time(delete_run_time):
        delete_notifications_older_than_retention_by_type(notification_type)

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


@freeze_time("2016-01-10 12:00:00.000000")
def test_should_not_delete_notification_history(sample_service, mocker):
    mocker.patch("app.dao.notifications_dao.get_s3_bucket_objects")
    with freeze_time('2016-01-01 12:00'):
        email_template, letter_template, sms_template = _create_templates(sample_service)
        create_notification(template=email_template, status='permanent-failure')
        create_notification(template=sms_template, status='permanent-failure')
        create_notification(template=letter_template, status='permanent-failure')
    assert Notification.query.count() == 3
    delete_notifications_older_than_retention_by_type('sms')
    assert Notification.query.count() == 2
    assert NotificationHistory.query.count() == 1


@pytest.mark.parametrize('notification_type', ['sms', 'email', 'letter'])
def test_delete_notifications_for_days_of_retention(sample_service, notification_type, mocker):
    mock_get_s3 = mocker.patch("app.dao.notifications_dao.get_s3_bucket_objects")
    create_test_data(notification_type, sample_service)
    assert Notification.query.count() == 9
    delete_notifications_older_than_retention_by_type(notification_type)
    assert Notification.query.count() == 7
    assert Notification.query.filter_by(notification_type=notification_type).count() == 1
    if notification_type == 'letter':
        assert mock_get_s3.call_count == 2
    else:
        mock_get_s3.assert_not_called()


@freeze_time('2019-09-01 04:30')
@pytest.mark.parametrize('notification_status', ['delivered', 'returned-letter', 'technical-failure'])
def test_delete_notifications_deletes_letters_from_s3(sample_letter_template, mocker, notification_status):
    mock_get_s3 = mocker.patch("app.dao.notifications_dao.get_s3_bucket_objects")
    eight_days_ago = datetime.utcnow() - timedelta(days=8)
    create_notification(
        template=sample_letter_template,
        status=notification_status,
        reference='LETTER_REF',
        created_at=eight_days_ago,
        sent_at=eight_days_ago
    )
    delete_notifications_older_than_retention_by_type(notification_type='letter')
    mock_get_s3.assert_called_once_with(bucket_name=current_app.config['LETTERS_PDF_BUCKET_NAME'],
                                        subfolder="{}/NOTIFY.LETTER_REF.D.2.C.C.{}.PDF".format(
                                            str(eight_days_ago.date()),
                                            eight_days_ago.strftime('%Y%m%d%H%M%S'))
                                        )


def test_delete_notifications_inserts_notification_history(sample_service):
    create_test_data('sms', sample_service)
    assert Notification.query.count() == 9
    delete_notifications_older_than_retention_by_type('sms')
    assert Notification.query.count() == 7

    assert NotificationHistory.query.count() == 2


def test_delete_notifications_does_nothing_if_notification_history_row_already_exists(
    sample_email_template, mocker
):
    mocker.patch("app.dao.notifications_dao.get_s3_bucket_objects")
    notification = create_notification(
        template=sample_email_template, created_at=datetime.utcnow() - timedelta(days=8),
        status='temporary-failure'
    )
    create_notification_history(
        id=notification.id, template=sample_email_template,
        created_at=datetime.utcnow() - timedelta(days=8), status='delivered'
    )

    delete_notifications_older_than_retention_by_type("email")

    history = NotificationHistory.query.all()
    assert len(history) == 1
    assert history[0].status == 'delivered'


def test_delete_notifications_keep_data_for_days_of_retention_is_longer(sample_service):
    create_test_data('sms', sample_service, 15)
    assert Notification.query.count() == 9
    delete_notifications_older_than_retention_by_type('sms')
    assert Notification.query.count() == 8
    assert Notification.query.filter(Notification.notification_type == 'sms').count() == 2


def test_delete_notifications_with_test_keys(sample_template, mocker):
    mocker.patch("app.dao.notifications_dao.get_s3_bucket_objects")
    create_notification(template=sample_template, key_type='test', created_at=datetime.utcnow() - timedelta(days=8))
    delete_notifications_older_than_retention_by_type('sms')
    assert Notification.query.count() == 0


def test_delete_notifications_delete_notification_type_for_default_time_if_no_days_of_retention_for_type(
        sample_service
):
    create_service_data_retention(service=sample_service, notification_type='sms',
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
    assert Notification.query.count() == 6
    delete_notifications_older_than_retention_by_type('email')
    assert Notification.query.count() == 5
    assert Notification.query.filter_by(notification_type='email').count() == 1


@pytest.mark.parametrize('notification_status', ['created', 'sending'])
def test_delete_notifications_doesnt_try_to_delete_from_s3_when_letter_has_not_finished_sending(
    sample_service, mocker, notification_status
):
    mock_get_s3 = mocker.patch("app.dao.notifications_dao.get_s3_bucket_objects")
    letter_template = create_template(service=sample_service, template_type='letter')

    create_notification(
        template=letter_template,
        status=notification_status,
        reference='LETTER_REF',
        created_at=datetime.utcnow() - timedelta(days=14)
    )
    delete_notifications_older_than_retention_by_type('letter', qry_limit=1)
    mock_get_s3.assert_not_called()


@freeze_time('2020-03-25 00:01')
def test_delete_notifications_calls_subquery_multiple_times(sample_template):
    create_notification(template=sample_template, created_at=datetime.now() - timedelta(days=7, minutes=3),
                        status='delivered')
    create_notification(template=sample_template, created_at=datetime.now() - timedelta(days=7, minutes=3),
                        status='delivered')
    create_notification(template=sample_template, created_at=datetime.now() - timedelta(days=7, minutes=3),
                        status='delivered')

    assert Notification.query.count() == 3
    delete_notifications_older_than_retention_by_type('sms', qry_limit=1)
    assert Notification.query.count() == 0


def test_delete_notifications_returns_sum_correctly(sample_template):
    create_notification(template=sample_template, created_at=datetime.now() - timedelta(days=8), status='delivered')
    create_notification(template=sample_template, created_at=datetime.now() - timedelta(days=8), status='delivered')

    s2 = create_service(service_name='s2')
    t2 = create_template(s2, template_type='sms')
    create_notification(template=t2, created_at=datetime.now() - timedelta(days=8), status='delivered')
    create_notification(template=t2, created_at=datetime.now() - timedelta(days=8), status='delivered')

    ret = delete_notifications_older_than_retention_by_type('sms', qry_limit=1)
    assert ret == 4


@freeze_time('2020-03-20 14:00')
def test_insert_notification_history_delete_notifications(sample_email_template):
    # should be deleted
    n1 = create_notification(template=sample_email_template,
                             created_at=datetime.utcnow() - timedelta(days=1, minutes=4), status='delivered')
    n2 = create_notification(template=sample_email_template,
                             created_at=datetime.utcnow() - timedelta(days=1, minutes=20), status='permanent-failure')
    n3 = create_notification(template=sample_email_template,
                             created_at=datetime.utcnow() - timedelta(days=1, minutes=30), status='temporary-failure')
    n4 = create_notification(template=sample_email_template,
                             created_at=datetime.utcnow() - timedelta(days=1, minutes=59), status='temporary-failure')
    n5 = create_notification(template=sample_email_template,
                             created_at=datetime.utcnow() - timedelta(days=1, hours=1), status='sending')
    n6 = create_notification(template=sample_email_template,
                             created_at=datetime.utcnow() - timedelta(days=1, minutes=61), status='pending')
    n7 = create_notification(template=sample_email_template,
                             created_at=datetime.utcnow() - timedelta(days=1, hours=1, seconds=1),
                             status='validation-failed')
    n8 = create_notification(template=sample_email_template,
                             created_at=datetime.utcnow() - timedelta(days=1, minutes=20), status='created')
    # should NOT be deleted - wrong status
    n9 = create_notification(template=sample_email_template,
                             created_at=datetime.utcnow() - timedelta(hours=1), status='delivered')
    n10 = create_notification(template=sample_email_template,
                              created_at=datetime.utcnow() - timedelta(hours=1), status='technical-failure')
    n11 = create_notification(template=sample_email_template,
                              created_at=datetime.utcnow() - timedelta(hours=23, minutes=59), status='created')

    ids_to_move = sorted([n1.id, n2.id, n3.id, n4.id, n5.id, n6.id, n7.id, n8.id])
    ids_to_keep = sorted([n9.id, n10.id, n11.id])
    del_count = insert_notification_history_delete_notifications(
        notification_type=sample_email_template.template_type,
        service_id=sample_email_template.service_id,
        timestamp_to_delete_backwards_from=datetime.utcnow() - timedelta(days=1))
    assert del_count == 8
    notifications = Notification.query.all()
    history_rows = NotificationHistory.query.all()
    assert len(history_rows) == 8
    assert ids_to_move == sorted([x.id for x in history_rows])
    assert len(notifications) == 3
    assert ids_to_keep == sorted([x.id for x in notifications])


def test_insert_notification_history_delete_notifications_more_notifications_than_query_limit(sample_template):
    create_notification(template=sample_template,
                        created_at=datetime.utcnow() + timedelta(minutes=4), status='delivered')
    create_notification(template=sample_template,
                        created_at=datetime.utcnow() + timedelta(minutes=20), status='permanent-failure')
    create_notification(template=sample_template,
                        created_at=datetime.utcnow() + timedelta(minutes=30), status='temporary-failure')

    del_count = insert_notification_history_delete_notifications(
        notification_type=sample_template.template_type,
        service_id=sample_template.service_id,
        timestamp_to_delete_backwards_from=datetime.utcnow() + timedelta(hours=1),
        qry_limit=1
    )

    assert del_count == 1
    notifications = Notification.query.all()
    history_rows = NotificationHistory.query.all()
    assert len(history_rows) == 1
    assert len(notifications) == 2


def test_insert_notification_history_delete_notifications_only_insert_delete_for_given_service(sample_email_template):
    notification_to_move = create_notification(template=sample_email_template,
                                               created_at=datetime.utcnow() + timedelta(minutes=4), status='delivered')
    another_service = create_service(service_name='Another service')
    another_template = create_template(service=another_service, template_type='email')
    notification_to_stay = create_notification(template=another_template,
                                               created_at=datetime.utcnow() + timedelta(minutes=4), status='delivered')

    del_count = insert_notification_history_delete_notifications(
        notification_type=sample_email_template.template_type,
        service_id=sample_email_template.service_id,
        timestamp_to_delete_backwards_from=datetime.utcnow() + timedelta(hours=1)
    )

    assert del_count == 1
    notifications = Notification.query.all()
    history_rows = NotificationHistory.query.all()
    assert len(notifications) == 1
    assert len(history_rows) == 1
    assert notifications[0].id == notification_to_stay.id
    assert history_rows[0], id == notification_to_move.id


def test_insert_notification_history_delete_notifications_insert_for_key_type(sample_template):
    create_notification(template=sample_template,
                        created_at=datetime.utcnow() - timedelta(hours=4),
                        status='delivered',
                        key_type='normal')
    create_notification(template=sample_template,
                        created_at=datetime.utcnow() - timedelta(hours=4),
                        status='delivered',
                        key_type='team')
    with_test_key = create_notification(template=sample_template,
                                        created_at=datetime.utcnow() - timedelta(hours=4),
                                        status='delivered',
                                        key_type='test')

    del_count = insert_notification_history_delete_notifications(
        notification_type=sample_template.template_type,
        service_id=sample_template.service_id,
        timestamp_to_delete_backwards_from=datetime.utcnow()
    )

    assert del_count == 2
    notifications = Notification.query.all()
    history_rows = NotificationHistory.query.all()
    assert len(notifications) == 1
    assert with_test_key.id == notifications[0].id
    assert len(history_rows) == 2
