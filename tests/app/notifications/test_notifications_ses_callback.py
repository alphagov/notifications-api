from datetime import datetime

from flask import json
from freezegun import freeze_time

from app import statsd_client
from app.dao.notifications_dao import get_notification_by_id
from app.models import Notification
from app.notifications.notifications_ses_callback import process_ses_response, remove_emails_from_bounce
from app.celery.research_mode_tasks import ses_hard_bounce_callback, ses_soft_bounce_callback, ses_notification_callback
from app.celery.service_callback_tasks import create_encrypted_callback_data

from tests.app.conftest import sample_notification as create_sample_notification
from tests.app.db import create_service_callback_api


def test_ses_callback_should_update_notification_status(
        client,
        notify_db,
        notify_db_session,
        sample_email_template,
        mocker):
    with freeze_time('2001-01-01T12:00:00'):
        mocker.patch('app.statsd_client.incr')
        mocker.patch('app.statsd_client.timing_with_dates')
        send_mock = mocker.patch(
            'app.celery.service_callback_tasks.send_delivery_status_to_service.apply_async'
        )
        notification = create_sample_notification(
            notify_db,
            notify_db_session,
            template=sample_email_template,
            reference='ref',
            status='sending',
            sent_at=datetime.utcnow()
        )
        callback_api = create_service_callback_api(service=sample_email_template.service,
                                                   url="https://original_url.com")
        assert get_notification_by_id(notification.id).status == 'sending'

        errors = process_ses_response(ses_notification_callback(reference='ref'))
        assert errors is None
        assert get_notification_by_id(notification.id).status == 'delivered'
        statsd_client.timing_with_dates.assert_any_call(
            "callback.ses.elapsed-time", datetime.utcnow(), notification.sent_at
        )
        statsd_client.incr.assert_any_call("callback.ses.delivered")
        updated_notification = Notification.query.get(notification.id)
        encrypted_data = create_encrypted_callback_data(updated_notification, callback_api)
        send_mock.assert_called_once_with([str(notification.id), encrypted_data], queue="service-callbacks")


def test_ses_callback_does_not_call_send_delivery_status_if_no_db_entry(
        client,
        notify_db,
        notify_db_session,
        sample_email_template,
        mocker):
    with freeze_time('2001-01-01T12:00:00'):

        send_mock = mocker.patch(
            'app.celery.service_callback_tasks.send_delivery_status_to_service.apply_async'
        )
        notification = create_sample_notification(
            notify_db,
            notify_db_session,
            template=sample_email_template,
            reference='ref',
            status='sending',
            sent_at=datetime.utcnow()
        )

        assert get_notification_by_id(notification.id).status == 'sending'

        errors = process_ses_response(ses_notification_callback(reference='ref'))
        assert errors is None
        assert get_notification_by_id(notification.id).status == 'delivered'

        send_mock.assert_not_called()


def test_ses_callback_should_update_multiple_notification_status_sent(
        client,
        notify_db,
        notify_db_session,
        sample_email_template,
        mocker):

    send_mock = mocker.patch(
        'app.celery.service_callback_tasks.send_delivery_status_to_service.apply_async'
    )
    create_sample_notification(
        notify_db,
        notify_db_session,
        template=sample_email_template,
        reference='ref1',
        sent_at=datetime.utcnow(),
        status='sending')

    create_sample_notification(
        notify_db,
        notify_db_session,
        template=sample_email_template,
        reference='ref2',
        sent_at=datetime.utcnow(),
        status='sending')

    create_sample_notification(
        notify_db,
        notify_db_session,
        template=sample_email_template,
        reference='ref3',
        sent_at=datetime.utcnow(),
        status='sending')
    create_service_callback_api(service=sample_email_template.service, url="https://original_url.com")
    assert process_ses_response(ses_notification_callback(reference='ref1')) is None
    assert process_ses_response(ses_notification_callback(reference='ref2')) is None
    assert process_ses_response(ses_notification_callback(reference='ref3')) is None
    assert send_mock.called


def test_ses_callback_should_set_status_to_temporary_failure(client,
                                                             notify_db,
                                                             notify_db_session,
                                                             sample_email_template,
                                                             mocker):
    send_mock = mocker.patch(
        'app.celery.service_callback_tasks.send_delivery_status_to_service.apply_async'
    )
    notification = create_sample_notification(
        notify_db,
        notify_db_session,
        template=sample_email_template,
        reference='ref',
        status='sending',
        sent_at=datetime.utcnow()
    )
    create_service_callback_api(service=notification.service, url="https://original_url.com")
    assert get_notification_by_id(notification.id).status == 'sending'
    assert process_ses_response(ses_soft_bounce_callback(reference='ref')) is None
    assert get_notification_by_id(notification.id).status == 'temporary-failure'
    assert send_mock.called


def test_ses_callback_should_not_set_status_once_status_is_delivered(client,
                                                                     notify_db,
                                                                     notify_db_session,
                                                                     sample_email_template,
                                                                     mocker):
    notification = create_sample_notification(
        notify_db,
        notify_db_session,
        template=sample_email_template,
        reference='ref',
        status='delivered',
        sent_at=datetime.utcnow()
    )

    assert get_notification_by_id(notification.id).status == 'delivered'


def test_ses_callback_should_set_status_to_permanent_failure(client,
                                                             notify_db,
                                                             notify_db_session,
                                                             sample_email_template,
                                                             mocker):
    send_mock = mocker.patch(
        'app.celery.service_callback_tasks.send_delivery_status_to_service.apply_async'
    )
    notification = create_sample_notification(
        notify_db,
        notify_db_session,
        template=sample_email_template,
        reference='ref',
        status='sending',
        sent_at=datetime.utcnow()
    )
    create_service_callback_api(service=sample_email_template.service, url="https://original_url.com")

    assert get_notification_by_id(notification.id).status == 'sending'
    assert process_ses_response(ses_hard_bounce_callback(reference='ref')) is None
    assert get_notification_by_id(notification.id).status == 'permanent-failure'
    assert send_mock.called


def test_remove_emails_from_bounce():
    # an actual bouncedict example
    message_dict = json.loads(ses_hard_bounce_callback(reference='ref')['Message'])

    remove_emails_from_bounce(message_dict['bounce'])

    assert 'not-real@gmail.com' not in json.dumps(message_dict)
