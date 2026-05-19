import uuid

import pytest
from celery.exceptions import Retry

from app.celery.process_replication_slot_changes import check_replication_slot_changes


def test_check_replication_slot_changes_early_returns_when_no_changes(mocker, caplog):
    mock_get_replication_changes = mocker.patch(
        "app.celery.process_replication_slot_changes.get_replication_changes", return_value=[]
    )
    mock_apply_insert = mocker.patch("app.celery.process_replication_slot_changes.apply_service_stats_insert")
    mock_apply_delete = mocker.patch("app.celery.process_replication_slot_changes.apply_service_stats_delete")
    mock_apply_update = mocker.patch("app.celery.process_replication_slot_changes.apply_service_stats_update_transition")

    with caplog.at_level("INFO"):
        check_replication_slot_changes()

    mock_get_replication_changes.assert_called_once_with(peek=False)
    mock_apply_insert.assert_not_called()
    mock_apply_delete.assert_not_called()
    mock_apply_update.assert_not_called()

    assert "No replication slot changes found" in caplog.messages


def test_check_replication_slot_changes_processes_insert_update_delete(mocker, caplog):
    service_id = str(uuid.uuid4())
    template_id = str(uuid.uuid4())
    changes = [
        {
            "type": "insert",
            "table": "notifications",
            "current_row_data": {
                "service_id": service_id,
                "template_id": template_id,
                "notification_type": "email",
                "notification_status": "created",
            },
            "previous_row_data": {},
        },
        {
            "type": "update",
            "table": "notifications",
            "current_row_data": {
                "service_id": service_id,
                "template_id": template_id,
                "notification_type": "email",
                "notification_status": "delivered",
            },
            "previous_row_data": {
                "service_id": service_id,
                "template_id": template_id,
                "notification_type": "email",
                "notification_status": "sending",
            },
        },
        {
            "type": "delete",
            "table": "notifications",
            "current_row_data": {
                "service_id": service_id,
                "template_id": template_id,
                "notification_type": "email",
                "notification_status": "delivered",
            },
            "previous_row_data": {},
        },
    ]

    mock_get_replication_changes = mocker.patch(
        "app.celery.process_replication_slot_changes.get_replication_changes", return_value=changes
    )
    mock_apply_insert = mocker.patch("app.celery.process_replication_slot_changes.apply_service_stats_insert")
    mock_apply_delete = mocker.patch("app.celery.process_replication_slot_changes.apply_service_stats_delete")
    mock_apply_update = mocker.patch("app.celery.process_replication_slot_changes.apply_service_stats_update_transition")

    with caplog.at_level("INFO"):
        check_replication_slot_changes()

    mock_get_replication_changes.assert_called_once_with(peek=False)
    mock_apply_insert.assert_called_once()
    mock_apply_update.assert_called_once()
    mock_apply_delete.assert_called_once()

    assert "Replication slot changes processed" in caplog.messages
    record = next(record for record in caplog.records if record.msg == "Replication slot changes processed")
    assert record.changes_count == 3
    assert record.processed_changes == 3
    assert record.ignored_changes == 0


def test_check_replication_slot_changes_calls_retry_on_query_error(mocker):
    mocker.patch(
        "app.celery.process_replication_slot_changes.get_replication_changes",
        side_effect=Exception("EXPECTED"),
    )
    mock_retry = mocker.patch.object(check_replication_slot_changes, "retry", side_effect=Retry("retry"))

    with pytest.raises(Retry):
        check_replication_slot_changes()

    assert mock_retry.call_count == 1
    _, kwargs = mock_retry.call_args
    assert kwargs["countdown"] == 1
