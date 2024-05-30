import uuid
from datetime import UTC, datetime

import pytest
from freezegun import freeze_time

from app import statsd_client
from app.celery.process_sms_client_response_tasks import (
    process_sms_client_response,
)
from app.clients import ClientException
from app.constants import NOTIFICATION_TECHNICAL_FAILURE


def test_process_sms_client_response_raises_error_if_reference_is_not_a_valid_uuid(client):
    with pytest.raises(ValueError):
        process_sms_client_response(status="000", provider_reference="something-bad", client_name="sms-client")


@pytest.mark.parametrize("client_name", ("Firetext", "MMG"))
def test_process_sms_response_raises_client_exception_for_unknown_status(
    sample_notification,
    mocker,
    client_name,
):
    with pytest.raises(ClientException) as e:
        process_sms_client_response(
            status="000",
            provider_reference=str(sample_notification.id),
            client_name=client_name,
        )

    assert f"{client_name} callback failed: status {'000'} not found." in str(e.value)
    assert sample_notification.status == NOTIFICATION_TECHNICAL_FAILURE


@pytest.mark.parametrize(
    "status, detailed_status_code, sms_provider, expected_notification_status, reason",
    [
        ("0", None, "Firetext", "delivered", None),
        ("1", "101", "Firetext", "permanent-failure", "Unknown Subscriber"),
        ("2", "102", "Firetext", "pending", "Absent Subscriber"),
        ("2", "1", "MMG", "permanent-failure", "Number does not exist"),
        ("3", "2", "MMG", "delivered", "Delivered to operator"),
        ("4", "27", "MMG", "temporary-failure", "Absent Subscriber"),
        ("5", "13", "MMG", "permanent-failure", "Sender id blacklisted"),
    ],
)
def test_process_sms_client_response_updates_notification_status(
    sample_notification, caplog, status, detailed_status_code, sms_provider, expected_notification_status, reason
):
    sample_notification.status = "sending"

    with caplog.at_level("INFO"):
        process_sms_client_response(status, str(sample_notification.id), sms_provider, detailed_status_code)

    message = f"{sms_provider} callback returned status of {expected_notification_status}({status}): {reason}({detailed_status_code}) for reference: {sample_notification.id}"  # noqa
    assert message in caplog.messages
    assert sample_notification.status == expected_notification_status


@pytest.mark.parametrize(
    "detailed_status_code, expected_notification_status, reason",
    [
        ("101", "permanent-failure", "Unknown Subscriber"),
        ("102", "temporary-failure", "Absent Subscriber"),
        (None, "temporary-failure", None),
        ("000", "temporary-failure", "No error reported"),
    ],
)
def test_process_sms_client_response_updates_notification_status_when_called_second_time(
    sample_notification, caplog, detailed_status_code, expected_notification_status, reason
):
    sample_notification.status = "sending"
    process_sms_client_response("2", str(sample_notification.id), "Firetext")

    with caplog.at_level("INFO"):
        process_sms_client_response("1", str(sample_notification.id), "Firetext", detailed_status_code)

    if detailed_status_code:
        message = f"Updating notification id {sample_notification.id} to status {expected_notification_status}, reason: {reason}"  # noqa
        assert message in caplog.messages

    assert sample_notification.status == expected_notification_status


@pytest.mark.parametrize("detailed_status_code", ["102", None, "000"])
def test_process_sms_client_response_updates_notification_status_to_pending_with_and_without_failure_code_present(
    sample_notification, mocker, detailed_status_code
):
    sample_notification.status = "sending"

    process_sms_client_response("2", str(sample_notification.id), "Firetext", detailed_status_code)

    assert sample_notification.status == "pending"


def test_process_sms_client_response_updates_notification_status_when_detailed_status_code_not_recognised(
    sample_notification, caplog
):
    sample_notification.status = "sending"
    process_sms_client_response("2", str(sample_notification.id), "Firetext")

    with caplog.at_level("WARNING"):
        process_sms_client_response("1", str(sample_notification.id), "Firetext", "789")

    assert "Failure code 789 from Firetext not recognised" in caplog.messages
    assert sample_notification.status == "temporary-failure"


def test_sms_response_does_not_send_callback_if_notification_is_not_in_the_db(sample_service, mocker):
    send_mock = mocker.patch("app.celery.process_sms_client_response_tasks.check_and_queue_callback_task")
    reference = str(uuid.uuid4())
    process_sms_client_response(status="3", provider_reference=reference, client_name="MMG")
    send_mock.assert_not_called()


@freeze_time("2001-01-01T12:00:00")
def test_process_sms_client_response_records_statsd_metrics(sample_notification, client, mocker):
    mocker.patch("app.statsd_client.incr")
    mocker.patch("app.statsd_client.timing_with_dates")

    sample_notification.status = "sending"
    sample_notification.sent_at = datetime.now(UTC).replace(tzinfo=None)

    process_sms_client_response("0", str(sample_notification.id), "Firetext")

    statsd_client.incr.assert_any_call("callback.firetext.delivered")
    statsd_client.timing_with_dates.assert_any_call(
        "callback.firetext.delivered.elapsed-time", datetime.now(UTC).replace(tzinfo=None), sample_notification.sent_at
    )


def test_process_sms_updates_billable_units_if_zero(sample_notification):
    sample_notification.billable_units = 0
    process_sms_client_response("3", str(sample_notification.id), "MMG")

    assert sample_notification.billable_units == 1


def test_process_sms_response_does_not_send_service_callback_for_pending_notifications(sample_notification, mocker):
    send_mock = mocker.patch("app.celery.process_sms_client_response_tasks.check_and_queue_callback_task")
    process_sms_client_response("2", str(sample_notification.id), "Firetext")
    send_mock.assert_not_called()


def test_outcome_statistics_called_for_successful_callback(sample_notification, mocker):
    send_mock = mocker.patch("app.celery.process_sms_client_response_tasks.check_and_queue_callback_task")
    reference = str(sample_notification.id)

    process_sms_client_response("3", reference, "MMG")
    send_mock.assert_called_once_with(sample_notification)


def test_process_sms_updates_sent_by_with_client_name_if_not_in_noti(sample_notification):
    sample_notification.sent_by = None
    process_sms_client_response("3", str(sample_notification.id), "MMG")

    assert sample_notification.sent_by == "mmg"
