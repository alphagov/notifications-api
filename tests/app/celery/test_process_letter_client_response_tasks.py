from datetime import datetime, timedelta

import pytest
from freezegun import freeze_time

from app.celery.process_letter_client_response_tasks import check_billable_units_by_id, process_letter_callback_data
from app.constants import (
    DVLA_NOTIFICATION_DISPATCHED,
    DVLA_NOTIFICATION_REJECTED,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_SENDING,
    NOTIFICATION_TECHNICAL_FAILURE,
)
from app.exceptions import NotificationTechnicalFailureException
from tests.app.db import create_notification_history


def test_check_billable_units_by_id_logs_error_if_billable_units_do_not_match_page_count(
    sample_letter_notification,
    caplog,
):
    check_billable_units_by_id(sample_letter_notification, 5)

    assert (
        f"Notification with id {sample_letter_notification.id} has 1 billable_units but DVLA says page count is 5"
    ) in caplog.messages


def test_process_letter_callback_data_checks_billable_units(mocker, sample_letter_notification):
    mock_check_billable_units = mocker.patch(
        "app.celery.process_letter_client_response_tasks.check_billable_units_by_id"
    )

    process_letter_callback_data(sample_letter_notification.id, 1, DVLA_NOTIFICATION_DISPATCHED)

    mock_check_billable_units.assert_called_once_with(sample_letter_notification, 1)


@freeze_time("2024-07-05T10:00:00")
def test_process_letter_callback_data_dao_update_notification_despatched_status(sample_letter_notification):
    assert sample_letter_notification.updated_at is None
    process_letter_callback_data(sample_letter_notification.id, 1, DVLA_NOTIFICATION_DISPATCHED)

    assert sample_letter_notification.status == NOTIFICATION_DELIVERED
    assert sample_letter_notification.updated_at == datetime.now()


@freeze_time("2024-07-05T10:00:00")
def test_process_letter_callback_data_dao_update_notification_rejected_status(sample_letter_notification):
    sample_letter_notification.updated_at = datetime.now() - timedelta(days=1)

    with pytest.raises(NotificationTechnicalFailureException):
        process_letter_callback_data(sample_letter_notification.id, 1, DVLA_NOTIFICATION_REJECTED)

    assert sample_letter_notification.status == NOTIFICATION_TECHNICAL_FAILURE
    assert sample_letter_notification.updated_at == datetime.now()


@freeze_time("2024-07-05T10:00:00")
def test_process_letter_callback_data_dao_update_notification_despatched_status_historical_notification(
    sample_letter_template,
):
    notification = create_notification_history(
        template=sample_letter_template,
        status=NOTIFICATION_SENDING,
    )

    notification.updated_at = datetime.now() - timedelta(days=1)

    process_letter_callback_data(notification.id, 1, DVLA_NOTIFICATION_DISPATCHED)

    assert notification.status == NOTIFICATION_DELIVERED
    assert notification.updated_at == datetime.now()


@freeze_time("2024-07-05T10:00:00")
def test_process_letter_callback_data_dao_update_notification_rejected_status_historical_notification(
    sample_letter_template,
):
    notification = create_notification_history(
        template=sample_letter_template,
        status=NOTIFICATION_SENDING,
    )

    notification.updated_at = datetime.now() - timedelta(days=1)

    with pytest.raises(NotificationTechnicalFailureException):
        process_letter_callback_data(notification.id, 1, DVLA_NOTIFICATION_REJECTED)

    assert notification.status == NOTIFICATION_TECHNICAL_FAILURE
    assert notification.updated_at == datetime.now()
