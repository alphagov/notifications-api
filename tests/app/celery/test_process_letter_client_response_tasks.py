from datetime import date, datetime, timedelta

import pytest
from freezegun import freeze_time

from app.celery.process_letter_client_response_tasks import (
    determine_new_status,
    process_letter_callback_data,
    validate_billable_units,
)
from app.constants import (
    DVLA_NOTIFICATION_DISPATCHED,
    DVLA_NOTIFICATION_REJECTED,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_SENDING,
    NOTIFICATION_TECHNICAL_FAILURE,
)
from app.exceptions import NotificationTechnicalFailureException
from app.models import LetterCostThreshold, NotificationLetterDespatch
from tests.app.db import create_notification_history


def test_mock_validate_billable_units_logs_error_if_billable_units_do_not_match_page_count(
    sample_letter_notification,
    caplog,
):
    validate_billable_units(sample_letter_notification, 5)

    assert (
        f"Notification with id {sample_letter_notification.id} has 1 billable_units but DVLA says page count is 5"
    ) in caplog.messages


def test_process_letter_callback_data_validate_billable_units(mocker, sample_letter_notification):
    mock_validate_billable_units = mocker.patch(
        "app.celery.process_letter_client_response_tasks.validate_billable_units"
    )

    process_letter_callback_data(
        str(sample_letter_notification.id),
        1,
        DVLA_NOTIFICATION_DISPATCHED,
        str(LetterCostThreshold.unsorted),
        date(2024, 8, 10).isoformat(),
    )

    mock_validate_billable_units.assert_called_once_with(sample_letter_notification, 1)


@freeze_time("2024-07-05T10:00:00")
def test_process_letter_callback_data_dao_update_notification_despatched_status(sample_letter_notification):
    assert sample_letter_notification.updated_at is None
    process_letter_callback_data(
        str(sample_letter_notification.id),
        1,
        DVLA_NOTIFICATION_DISPATCHED,
        str(LetterCostThreshold.unsorted),
        date(2024, 7, 9).isoformat(),
    )

    assert sample_letter_notification.status == NOTIFICATION_DELIVERED
    assert sample_letter_notification.updated_at == datetime.now()

    letter_despatch = NotificationLetterDespatch.query.one()
    assert letter_despatch.notification_id == sample_letter_notification.id
    assert letter_despatch.despatched_on == date(2024, 7, 9)
    assert letter_despatch.cost_threshold == LetterCostThreshold.unsorted


@freeze_time("2024-07-05T10:00:00")
def test_process_letter_callback_data_dao_update_notification_rejected_status(sample_letter_notification, mocker):
    mock_update_letter_despatch = mocker.patch(
        "app.celery.process_letter_client_response_tasks.dao_record_letter_despatched_on_by_id"
    )

    sample_letter_notification.updated_at = datetime.now() - timedelta(days=1)

    with pytest.raises(NotificationTechnicalFailureException):
        process_letter_callback_data(
            str(sample_letter_notification.id),
            1,
            DVLA_NOTIFICATION_REJECTED,
            str(LetterCostThreshold.sorted),
            date(2024, 7, 8).isoformat(),
        )

    assert sample_letter_notification.status == NOTIFICATION_TECHNICAL_FAILURE
    assert sample_letter_notification.updated_at == datetime.now()
    assert not mock_update_letter_despatch.called


@freeze_time("2024-07-05T10:00:00")
def test_process_letter_callback_data_dao_update_notification_despatched_status_historical_notification(
    sample_letter_template,
):
    notification = create_notification_history(
        template=sample_letter_template,
        status=NOTIFICATION_SENDING,
    )

    notification.updated_at = datetime.now() - timedelta(days=1)

    process_letter_callback_data(
        str(notification.id),
        1,
        DVLA_NOTIFICATION_DISPATCHED,
        str(LetterCostThreshold.sorted),
        date(2024, 7, 10).isoformat(),
    )

    assert notification.status == NOTIFICATION_DELIVERED
    assert notification.updated_at == datetime.now()

    letter_despatch = NotificationLetterDespatch.query.one()
    assert letter_despatch.notification_id == notification.id
    assert letter_despatch.despatched_on == date(2024, 7, 10)
    assert letter_despatch.cost_threshold == LetterCostThreshold.sorted


@freeze_time("2024-07-05T10:00:00")
def test_process_letter_callback_data_dao_update_notification_rejected_status_historical_notification(
    sample_letter_template,
    mocker,
):
    mock_update_letter_despatch = mocker.patch(
        "app.celery.process_letter_client_response_tasks.dao_record_letter_despatched_on_by_id"
    )

    notification = create_notification_history(
        template=sample_letter_template,
        status=NOTIFICATION_SENDING,
    )

    notification.updated_at = datetime.now() - timedelta(days=1)

    with pytest.raises(NotificationTechnicalFailureException):
        process_letter_callback_data(
            str(notification.id),
            1,
            DVLA_NOTIFICATION_REJECTED,
            str(LetterCostThreshold.unsorted),
            date(2024, 3, 1).isoformat(),
        )

    assert notification.status == NOTIFICATION_TECHNICAL_FAILURE
    assert notification.updated_at == datetime.now()
    assert not mock_update_letter_despatch.called


@freeze_time("2024-07-05T10:00:00")
def test_process_letter_callback_data_duplicate_update(sample_letter_notification, caplog, mocker):
    mock_update_letter_despatch = mocker.patch(
        "app.celery.process_letter_client_response_tasks.dao_record_letter_despatched_on_by_id"
    )

    yesterday = datetime.now() - timedelta(days=1)

    initial_status = NOTIFICATION_DELIVERED
    sample_letter_notification.status = initial_status
    sample_letter_notification.updated_at = yesterday

    process_letter_callback_data(
        str(sample_letter_notification.id),
        1,
        DVLA_NOTIFICATION_DISPATCHED,
        str(LetterCostThreshold.unsorted),
        date(2024, 7, 8).isoformat(),
    )

    assert sample_letter_notification.status == initial_status
    assert sample_letter_notification.updated_at == yesterday

    assert any(
        f"Duplicate callback received for service {sample_letter_notification.service_id}. "
        f"Notification ID {sample_letter_notification.id} with type letter sent by None. "
        f"New status was {sample_letter_notification.status}, current status is {initial_status}." in message
        for message in caplog.messages
    )

    assert not mock_update_letter_despatch.called


@pytest.mark.parametrize(
    "dvla_status, expected_status",
    [
        (DVLA_NOTIFICATION_DISPATCHED, NOTIFICATION_DELIVERED),
        (DVLA_NOTIFICATION_REJECTED, NOTIFICATION_TECHNICAL_FAILURE),
    ],
)
def test_determine_new_status(dvla_status, expected_status):
    assert determine_new_status(dvla_status) == expected_status
