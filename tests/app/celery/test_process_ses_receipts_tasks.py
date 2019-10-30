import json
from datetime import datetime


from freezegun import freeze_time


from app import statsd_client, encryption
from app.celery.process_ses_receipts_tasks import process_ses_results
from app.celery.research_mode_tasks import ses_hard_bounce_callback, ses_soft_bounce_callback, ses_notification_callback
from app.celery.service_callback_tasks import create_delivery_status_callback_data
from app.dao.notifications_dao import get_notification_by_id
from app.models import Complaint, Notification
from app.notifications.notifications_ses_callback import remove_emails_from_complaint, remove_emails_from_bounce

from tests.app.db import (
    create_notification,
    ses_complaint_callback,
    create_service_callback_api,
)


def test_process_ses_results(sample_email_template):
    create_notification(sample_email_template, reference='ref1', sent_at=datetime.utcnow(), status='sending')

    assert process_ses_results(response=ses_notification_callback(reference='ref1'))


def test_process_ses_results_retry_called(sample_email_template, notify_db, mocker):
    create_notification(sample_email_template, reference='ref1', sent_at=datetime.utcnow(), status='sending')

    mocker.patch("app.dao.notifications_dao._update_notification_status", side_effect=Exception("EXPECTED"))
    mocked = mocker.patch('app.celery.process_ses_receipts_tasks.process_ses_results.retry')
    process_ses_results(response=ses_notification_callback(reference='ref1'))
    assert mocked.call_count != 0


def test_process_ses_results_in_complaint(sample_email_template, mocker):
    notification = create_notification(template=sample_email_template, reference='ref1')
    mocked = mocker.patch("app.dao.notifications_dao.update_notification_status_by_reference")
    process_ses_results(response=ses_complaint_callback())
    assert mocked.call_count == 0
    complaints = Complaint.query.all()
    assert len(complaints) == 1
    assert complaints[0].notification_id == notification.id


def test_remove_emails_from_complaint():
    test_json = json.loads(ses_complaint_callback()['Message'])
    remove_emails_from_complaint(test_json)
    assert "recipient1@example.com" not in json.dumps(test_json)


def test_remove_email_from_bounce():
    test_json = json.loads(ses_hard_bounce_callback(reference='ref1')['Message'])
    remove_emails_from_bounce(test_json)
    assert "bounce@simulator.amazonses.com" not in json.dumps(test_json)


def test_ses_callback_should_update_notification_status(
        client,
        notify_db_session,
        sample_email_template,
        mocker):
    with freeze_time('2001-01-01T12:00:00'):
        mocker.patch('app.statsd_client.incr')
        mocker.patch('app.statsd_client.timing_with_dates')
        send_mock = mocker.patch(
            'app.celery.service_callback_tasks.send_delivery_status_to_service.apply_async'
        )
        notification = create_notification(
            template=sample_email_template,
            status='sending',
            reference='ref',
        )
        callback_api = create_service_callback_api(service=sample_email_template.service,
                                                   url="https://original_url.com")
        assert get_notification_by_id(notification.id).status == 'sending'

        assert process_ses_results(ses_notification_callback(reference='ref'))
        assert get_notification_by_id(notification.id).status == 'delivered'
        statsd_client.timing_with_dates.assert_any_call(
            "callback.ses.elapsed-time", datetime.utcnow(), notification.sent_at
        )
        statsd_client.incr.assert_any_call("callback.ses.delivered")
        updated_notification = Notification.query.get(notification.id)
        encrypted_data = create_delivery_status_callback_data(updated_notification, callback_api)
        send_mock.assert_called_once_with([str(notification.id), encrypted_data], queue="service-callbacks")


def test_ses_callback_should_not_update_notification_status_if_already_delivered(sample_email_template, mocker):
    mock_dup = mocker.patch('app.celery.process_ses_receipts_tasks.notifications_dao._duplicate_update_warning')
    mock_upd = mocker.patch('app.celery.process_ses_receipts_tasks.notifications_dao._update_notification_status')
    notification = create_notification(template=sample_email_template, reference='ref', status='delivered')

    assert process_ses_results(ses_notification_callback(reference='ref')) is None
    assert get_notification_by_id(notification.id).status == 'delivered'

    mock_dup.assert_called_once_with(notification, 'delivered')
    assert mock_upd.call_count == 0


def test_ses_callback_should_retry_if_notification_is_new(client, notify_db, mocker):
    mock_retry = mocker.patch('app.celery.process_ses_receipts_tasks.process_ses_results.retry')
    mock_logger = mocker.patch('app.celery.process_ses_receipts_tasks.current_app.logger.error')

    with freeze_time('2017-11-17T12:14:03.646Z'):
        assert process_ses_results(ses_notification_callback(reference='ref')) is None
        assert mock_logger.call_count == 0
        assert mock_retry.call_count == 1


def test_ses_callback_should_log_if_notification_is_missing(client, notify_db, mocker):
    mock_retry = mocker.patch('app.celery.process_ses_receipts_tasks.process_ses_results.retry')
    mock_logger = mocker.patch('app.celery.process_ses_receipts_tasks.current_app.logger.warning')

    with freeze_time('2017-11-17T12:34:03.646Z'):
        assert process_ses_results(ses_notification_callback(reference='ref')) is None
        assert mock_retry.call_count == 0
        mock_logger.assert_called_once_with('notification not found for reference: ref (update to delivered)')


def test_ses_callback_should_not_retry_if_notification_is_old(client, notify_db, mocker):
    mock_retry = mocker.patch('app.celery.process_ses_receipts_tasks.process_ses_results.retry')
    mock_logger = mocker.patch('app.celery.process_ses_receipts_tasks.current_app.logger.error')

    with freeze_time('2017-11-21T12:14:03.646Z'):
        assert process_ses_results(ses_notification_callback(reference='ref')) is None
        assert mock_logger.call_count == 0
        assert mock_retry.call_count == 0


def test_ses_callback_does_not_call_send_delivery_status_if_no_db_entry(
        client,
        notify_db_session,
        sample_email_template,
        mocker):
    with freeze_time('2001-01-01T12:00:00'):

        send_mock = mocker.patch(
            'app.celery.service_callback_tasks.send_delivery_status_to_service.apply_async'
        )
        notification = create_notification(
            template=sample_email_template,
            status='sending',
            reference='ref',
        )

        assert get_notification_by_id(notification.id).status == 'sending'

        assert process_ses_results(ses_notification_callback(reference='ref'))
        assert get_notification_by_id(notification.id).status == 'delivered'

        send_mock.assert_not_called()


def test_ses_callback_should_update_multiple_notification_status_sent(
        client,
        notify_db_session,
        sample_email_template,
        mocker):

    send_mock = mocker.patch(
        'app.celery.service_callback_tasks.send_delivery_status_to_service.apply_async'
    )
    create_notification(
        template=sample_email_template,
        status='sending',
        reference='ref1',
    )
    create_notification(
        template=sample_email_template,
        status='sending',
        reference='ref2',
    )
    create_notification(
        template=sample_email_template,
        status='sending',
        reference='ref3',
    )
    create_service_callback_api(service=sample_email_template.service, url="https://original_url.com")
    assert process_ses_results(ses_notification_callback(reference='ref1'))
    assert process_ses_results(ses_notification_callback(reference='ref2'))
    assert process_ses_results(ses_notification_callback(reference='ref3'))
    assert send_mock.called


def test_ses_callback_should_set_status_to_temporary_failure(client,
                                                             notify_db_session,
                                                             sample_email_template,
                                                             mocker):
    send_mock = mocker.patch(
        'app.celery.service_callback_tasks.send_delivery_status_to_service.apply_async'
    )
    notification = create_notification(
        template=sample_email_template,
        status='sending',
        reference='ref',
    )
    create_service_callback_api(service=notification.service, url="https://original_url.com")
    assert get_notification_by_id(notification.id).status == 'sending'
    assert process_ses_results(ses_soft_bounce_callback(reference='ref'))
    assert get_notification_by_id(notification.id).status == 'temporary-failure'
    assert send_mock.called


def test_ses_callback_should_set_status_to_permanent_failure(client,
                                                             notify_db_session,
                                                             sample_email_template,
                                                             mocker):
    send_mock = mocker.patch(
        'app.celery.service_callback_tasks.send_delivery_status_to_service.apply_async'
    )
    notification = create_notification(
        template=sample_email_template,
        status='sending',
        reference='ref',
    )
    create_service_callback_api(service=sample_email_template.service, url="https://original_url.com")

    assert get_notification_by_id(notification.id).status == 'sending'
    assert process_ses_results(ses_hard_bounce_callback(reference='ref'))
    assert get_notification_by_id(notification.id).status == 'permanent-failure'
    assert send_mock.called


def test_ses_callback_should_send_on_complaint_to_user_callback_api(sample_email_template, mocker):
    send_mock = mocker.patch(
        'app.celery.service_callback_tasks.send_complaint_to_service.apply_async'
    )
    create_service_callback_api(
        service=sample_email_template.service, url="https://original_url.com", callback_type="complaint"
    )

    notification = create_notification(
        template=sample_email_template, reference='ref1', sent_at=datetime.utcnow(), status='sending'
    )
    response = ses_complaint_callback()
    assert process_ses_results(response)

    assert send_mock.call_count == 1
    assert encryption.decrypt(send_mock.call_args[0][0][0]) == {
        'complaint_date': '2018-06-05T13:59:58.000000Z',
        'complaint_id': str(Complaint.query.one().id),
        'notification_id': str(notification.id),
        'reference': None,
        'service_callback_api_bearer_token': 'some_super_secret',
        'service_callback_api_url': 'https://original_url.com',
        'to': 'recipient1@example.com'
    }
