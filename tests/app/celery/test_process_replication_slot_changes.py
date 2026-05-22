import uuid
from datetime import datetime

import pytest
from celery.exceptions import Retry

from app.celery.process_replication_slot_changes import check_replication_slot_changes


def _base_row(service_id: str, template_id: str, *, status: str):
    return {
        "service_id": service_id,
        "template_id": template_id,
        "notification_type": "email",
        "notification_status": status,
        "key_type": "normal",
        "created_at": datetime.utcnow().isoformat(),
    }


def test_check_replication_slot_changes_early_returns_when_no_changes(mocker, caplog):
    mocker.patch("app.celery.process_replication_slot_changes._try_advisory_lock", return_value=True)
    mock_unlock = mocker.patch("app.celery.process_replication_slot_changes._advisory_unlock")
    mock_get_replication_changes = mocker.patch(
        "app.celery.process_replication_slot_changes.get_replication_changes", return_value=[]
    )
    mock_commit = mocker.patch("app.celery.process_replication_slot_changes.db.session.commit")
    mock_advance = mocker.patch("app.celery.process_replication_slot_changes._advance_replication_slot")
    mock_apply_delta = mocker.patch("app.celery.process_replication_slot_changes.apply_service_stats_delta")

    with caplog.at_level("INFO"):
        check_replication_slot_changes()

    mock_get_replication_changes.assert_called_once()
    mock_apply_delta.assert_not_called()
    mock_commit.assert_not_called()
    mock_advance.assert_not_called()
    mock_unlock.assert_called_once()

    assert "No replication slot changes found" in caplog.messages


def test_check_replication_slot_changes_rolls_up_and_advances_slot(mocker, caplog):
    service_id = str(uuid.uuid4())
    template_id = str(uuid.uuid4())
    changes = [
        {
            "type": "insert",
            "table": "notifications",
            "nextlsn": "0/16B6A28",
            "current_row_data": _base_row(service_id, template_id, status="created"),
            "previous_row_data": {},
        },
        {
            "type": "update",
            "table": "notifications",
            "nextlsn": "0/16B6A28",
            "current_row_data": _base_row(service_id, template_id, status="sending"),
            "previous_row_data": _base_row(service_id, template_id, status="created"),
        },
        {
            "type": "delete",
            "table": "notification_history",
            "nextlsn": "0/16B6A28",
            "current_row_data": {},
            "previous_row_data": _base_row(service_id, template_id, status="delivered"),
        },
    ]

    mocker.patch("app.celery.process_replication_slot_changes._try_advisory_lock", return_value=True)
    mocker.patch("app.celery.process_replication_slot_changes._advisory_unlock")
    mocker.patch("app.celery.process_replication_slot_changes.get_replication_changes", return_value=changes)

    call_order = []

    def commit_side_effect():
        call_order.append("commit")

    def advance_side_effect(_):
        call_order.append("advance")

    mock_commit = mocker.patch("app.celery.process_replication_slot_changes.db.session.commit", side_effect=commit_side_effect)
    mock_advance = mocker.patch(
        "app.celery.process_replication_slot_changes._advance_replication_slot", side_effect=advance_side_effect
    )
    mock_apply_delta = mocker.patch("app.celery.process_replication_slot_changes.apply_service_stats_delta")

    with caplog.at_level("INFO"):
        check_replication_slot_changes()

    mock_commit.assert_called_once()
    mock_advance.assert_called_once_with("0/16B6A28")
    assert call_order == ["commit", "advance"]

    assert mock_apply_delta.call_count == 1
    dimensions, delta = mock_apply_delta.call_args.args
    assert str(dimensions["service_id"]) == service_id
    assert str(dimensions["template_id"]) == template_id
    assert dimensions["notification_type"] == "email"
    assert dimensions["notification_status"] == "sending"
    assert delta == 1

    assert "Replication slot changes processed" in caplog.messages


def test_check_replication_slot_changes_returns_when_lock_not_acquired(mocker):
    mocker.patch("app.celery.process_replication_slot_changes._try_advisory_lock", return_value=False)
    mock_get_replication_changes = mocker.patch("app.celery.process_replication_slot_changes.get_replication_changes")
    mock_unlock = mocker.patch("app.celery.process_replication_slot_changes._advisory_unlock")

    check_replication_slot_changes()

    mock_get_replication_changes.assert_not_called()
    mock_unlock.assert_not_called()


def test_check_replication_slot_changes_calls_retry_on_query_error(mocker):
    mocker.patch("app.celery.process_replication_slot_changes._try_advisory_lock", return_value=True)
    mock_unlock = mocker.patch("app.celery.process_replication_slot_changes._advisory_unlock")
    mocker.patch(
        "app.celery.process_replication_slot_changes.get_replication_changes",
        side_effect=Exception("EXPECTED"),
    )
    mock_retry = mocker.patch.object(check_replication_slot_changes, "retry", side_effect=Retry("retry"))
    mock_rollback = mocker.patch("app.celery.process_replication_slot_changes.db.session.rollback")

    with pytest.raises(Retry):
        check_replication_slot_changes()

    assert mock_retry.call_count == 1
    mock_rollback.assert_called_once()
    mock_unlock.assert_called_once()
    _, kwargs = mock_retry.call_args
    assert kwargs["countdown"] == 1
