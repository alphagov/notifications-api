import json
from datetime import UTC, datetime

from freezegun import freeze_time

from app import signing, statsd_client
from app.celery.process_ses_receipts_tasks import process_ses_results
from app.celery.research_mode_tasks import (
    ses_hard_bounce_callback,
    ses_notification_callback,
    ses_soft_bounce_callback,
)
from app.dao.notifications_dao import get_notification_by_id
from app.models import Complaint, Notification
from app.notifications.notifications_ses_callback import (
    remove_emails_from_bounce,
    remove_emails_from_complaint,
)
from tests.app.db import (
    create_notification,
    create_service_callback_api,
    ses_complaint_callback,
)


def test_process_ses_results(sample_email_template):
    create_notification(
        sample_email_template, reference="ref1", sent_at=datetime.now(UTC).replace(tzinfo=None), status="sending"
    )

    assert process_ses_results(response=ses_notification_callback(reference="ref1"))


def test_process_ses_results_retry_called(sample_email_template, mocker):
    create_notification(
        sample_email_template, reference="ref1", sent_at=datetime.now(UTC).replace(tzinfo=None), status="sending"
    )

    mocker.patch("app.dao.notifications_dao.dao_update_notifications_by_reference", side_effect=Exception("EXPECTED"))
    mocked = mocker.patch("app.celery.process_ses_receipts_tasks.process_ses_results.retry")
    process_ses_results(response=ses_notification_callback(reference="ref1"))
    assert mocked.call_count != 0


def test_process_ses_results_in_complaint(sample_email_template, mocker):
    notification = create_notification(template=sample_email_template, reference="ref1")
    old_updated_at = notification.updated_at
    process_ses_results(response=ses_complaint_callback())
    complaints = Complaint.query.all()
    assert len(complaints) == 1
    assert complaints[0].notification_id == notification.id
    # assert notification has not been modified
    assert notification.updated_at == old_updated_at


def test_remove_emails_from_complaint():
    test_json = json.loads(ses_complaint_callback()["Message"])
    remove_emails_from_complaint(test_json)
    assert "recipient1@example.com" not in json.dumps(test_json)


def test_remove_email_from_bounce():
    test_json = json.loads(ses_hard_bounce_callback(reference="ref1")["Message"])
    remove_emails_from_bounce(test_json)
    assert "bounce@simulator.amazonses.com" not in json.dumps(test_json)


def test_ses_callback_should_update_notification_status(client, notify_db_session, sample_email_template, mocker):
    with freeze_time("2001-01-01T12:00:00"):
        mocker.patch("app.statsd_client.incr")
        mocker.patch("app.statsd_client.timing_with_dates")
        send_mock = mocker.patch("app.celery.process_ses_receipts_tasks.check_and_queue_callback_task")
        notification = create_notification(
            template=sample_email_template,
            status="sending",
            reference="ref",
        )
        assert get_notification_by_id(notification.id).status == "sending"

        assert process_ses_results(ses_notification_callback(reference="ref"))
        assert get_notification_by_id(notification.id).status == "delivered"
        statsd_client.timing_with_dates.assert_any_call(
            "callback.ses.delivered.elapsed-time", datetime.now(UTC).replace(tzinfo=None), notification.sent_at
        )
        statsd_client.incr.assert_any_call("callback.ses.delivered")
        updated_notification = Notification.query.get(notification.id)
        send_mock.assert_called_once_with(updated_notification)


def test_ses_callback_should_not_update_notification_status_if_already_delivered(sample_email_template, mocker):
    mock_dup = mocker.patch("app.celery.process_ses_receipts_tasks.notifications_dao._duplicate_update_warning")
    mock_upd = mocker.patch(
        "app.celery.process_ses_receipts_tasks.notifications_dao.dao_update_notifications_by_reference"
    )
    notification = create_notification(template=sample_email_template, reference="ref", status="delivered")

    assert process_ses_results(ses_notification_callback(reference="ref")) is None
    assert get_notification_by_id(notification.id).status == "delivered"

    mock_dup.assert_called_once_with(notification=notification, status="delivered")
    assert mock_upd.call_count == 0


def test_ses_callback_should_retry_if_notification_is_new(client, notify_db_session, mocker, caplog):
    mock_retry = mocker.patch("app.celery.process_ses_receipts_tasks.process_ses_results.retry")

    with freeze_time("2017-11-17T12:14:03.646Z"), caplog.at_level("ERROR"):
        assert process_ses_results(ses_notification_callback(reference="ref")) is None

    assert caplog.messages == []
    assert mock_retry.call_count == 1


def test_ses_callback_should_log_if_notification_is_missing(client, notify_db_session, mocker, caplog):
    mock_retry = mocker.patch("app.celery.process_ses_receipts_tasks.process_ses_results.retry")

    with freeze_time("2017-11-17T12:34:03.646Z"), caplog.at_level("WARNING"):
        assert process_ses_results(ses_notification_callback(reference="ref")) is None

    assert "notification not found for reference: ref (update to delivered)" in caplog.messages
    assert mock_retry.call_count == 0


def test_ses_callback_should_not_retry_if_notification_is_old(client, notify_db_session, mocker, caplog):
    mock_retry = mocker.patch("app.celery.process_ses_receipts_tasks.process_ses_results.retry")

    with freeze_time("2017-11-21T12:14:03.646Z"), caplog.at_level("ERROR"):
        assert process_ses_results(ses_notification_callback(reference="ref")) is None

    assert caplog.messages == []
    assert mock_retry.call_count == 0


def test_ses_callback_should_update_multiple_notification_status_sent(
    client, notify_db_session, sample_email_template, mocker
):
    send_mock = mocker.patch("app.celery.process_ses_receipts_tasks.check_and_queue_callback_task")
    create_notification(
        template=sample_email_template,
        status="sending",
        reference="ref1",
    )
    create_notification(
        template=sample_email_template,
        status="sending",
        reference="ref2",
    )
    create_notification(
        template=sample_email_template,
        status="sending",
        reference="ref3",
    )
    assert process_ses_results(ses_notification_callback(reference="ref1"))
    assert process_ses_results(ses_notification_callback(reference="ref2"))
    assert process_ses_results(ses_notification_callback(reference="ref3"))
    assert send_mock.called


def test_ses_callback_should_set_status_to_temporary_failure(
    client, notify_db_session, sample_email_template, mocker, caplog
):
    send_mock = mocker.patch("app.celery.process_ses_receipts_tasks.check_and_queue_callback_task")

    with caplog.at_level("INFO"):
        notification = create_notification(
            template=sample_email_template,
            status="sending",
            reference="ref",
        )
        assert get_notification_by_id(notification.id).status == "sending"
        assert process_ses_results(ses_soft_bounce_callback(reference="ref"))
        assert get_notification_by_id(notification.id).status == "temporary-failure"

    assert send_mock.called
    assert f"SES bounce for notification ID {notification.id}" in caplog.messages


def test_ses_callback_should_set_status_to_permanent_failure(
    client, notify_db_session, sample_email_template, mocker, caplog
):
    send_mock = mocker.patch("app.celery.process_ses_receipts_tasks.check_and_queue_callback_task")

    with caplog.at_level("INFO"):
        notification = create_notification(
            template=sample_email_template,
            status="sending",
            reference="ref",
        )
        assert get_notification_by_id(notification.id).status == "sending"
        assert process_ses_results(ses_hard_bounce_callback(reference="ref"))
        assert get_notification_by_id(notification.id).status == "permanent-failure"

    assert send_mock.called

    bounce_record = next(
        filter(lambda r: r.message == f"SES bounce for notification ID {notification.id}", caplog.records), None
    )
    assert bounce_record is not None
    assert hasattr(bounce_record, "bounce_message")


def test_ses_callback_should_send_on_complaint_to_user_callback_api(sample_email_template, mocker):
    send_mock = mocker.patch("app.celery.service_callback_tasks.send_complaint_to_service.apply_async")
    create_service_callback_api(
        service=sample_email_template.service, url="https://original_url.com", callback_type="complaint"
    )

    notification = create_notification(
        template=sample_email_template,
        reference="ref1",
        sent_at=datetime.now(UTC).replace(tzinfo=None),
        status="sending",
    )
    response = ses_complaint_callback()
    assert process_ses_results(response)

    assert send_mock.call_count == 1
    assert signing.decode(send_mock.call_args[0][0][0]) == {
        "complaint_date": "2018-06-05T13:59:58.000000Z",
        "complaint_id": str(Complaint.query.one().id),
        "notification_id": str(notification.id),
        "reference": None,
        "service_callback_api_bearer_token": "some_super_secret",
        "service_callback_api_url": "https://original_url.com",
        "to": "recipient1@example.com",
    }
