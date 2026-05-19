import uuid

import pytest
from celery.exceptions import Retry

from app.celery.process_replication_slot_changes import check_replication_slot_changes


def test_check_replication_slot_changes_early_returns_when_no_changes(mocker, caplog):
    mock_get_replication_changes = mocker.patch(
        "app.celery.process_replication_slot_changes.get_replication_changes", return_value=[]
    )
    mock_commit = mocker.patch("app.celery.process_replication_slot_changes.db.session.commit")
    mock_apply_insert = mocker.patch("app.celery.process_replication_slot_changes.apply_service_stats_insert")
    mock_apply_delete = mocker.patch("app.celery.process_replication_slot_changes.apply_service_stats_delete")
    mock_apply_update = mocker.patch("app.celery.process_replication_slot_changes.apply_service_stats_update_transition")

    with caplog.at_level("INFO"):
        check_replication_slot_changes()

    mock_get_replication_changes.assert_called_once_with(peek=False)
    mock_apply_insert.assert_not_called()
    mock_apply_delete.assert_not_called()
    mock_apply_update.assert_not_called()
    mock_commit.assert_not_called()

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
    mock_commit = mocker.patch("app.celery.process_replication_slot_changes.db.session.commit")
    mock_apply_insert = mocker.patch("app.celery.process_replication_slot_changes.apply_service_stats_insert")
    mock_apply_delete = mocker.patch("app.celery.process_replication_slot_changes.apply_service_stats_delete")
    mock_apply_update = mocker.patch("app.celery.process_replication_slot_changes.apply_service_stats_update_transition")

    with caplog.at_level("INFO"):
        check_replication_slot_changes()

    mock_get_replication_changes.assert_called_once_with(peek=False)
    mock_apply_insert.assert_called_once()
    mock_apply_update.assert_called_once()
    mock_apply_delete.assert_called_once()
    mock_commit.assert_called_once()

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
    mock_rollback = mocker.patch("app.celery.process_replication_slot_changes.db.session.rollback")

    with pytest.raises(Retry):
        check_replication_slot_changes()

    assert mock_retry.call_count == 1
    mock_rollback.assert_called_once()
    _, kwargs = mock_retry.call_args
    assert kwargs["countdown"] == 1


def test_check_replication_slot_changes_update_with_sparse_previous_status_uses_transition(mocker):
    service_id = str(uuid.uuid4())
    template_id = str(uuid.uuid4())
    changes = [
        {
            "type": "update",
            "table": "notifications",
            "current_row_data": {
                "service_id": service_id,
                "template_id": template_id,
                "notification_type": "sms",
                "notification_status": "sending",
            },
            "previous_row_data": {
                "id": str(uuid.uuid4()),
                "notification_status": "created",
            },
        }
    ]

    mocker.patch("app.celery.process_replication_slot_changes.get_replication_changes", return_value=changes)
    mock_commit = mocker.patch("app.celery.process_replication_slot_changes.db.session.commit")
    mock_apply_insert = mocker.patch("app.celery.process_replication_slot_changes.apply_service_stats_insert")
    mock_apply_update = mocker.patch("app.celery.process_replication_slot_changes.apply_service_stats_update_transition")

    check_replication_slot_changes()

    mock_apply_insert.assert_not_called()
    mock_apply_update.assert_called_once()
    old_dimensions, new_dimensions = mock_apply_update.call_args.args
    assert old_dimensions["notification_status"] == "created"
    assert new_dimensions["notification_status"] == "sending"
    assert str(old_dimensions["service_id"]) == service_id
    assert str(old_dimensions["template_id"]) == template_id
    assert old_dimensions["notification_type"] == "sms"
    mock_commit.assert_called_once()


def test_check_replication_slot_changes_update_without_previous_status_uses_insert(mocker):
    service_id = str(uuid.uuid4())
    template_id = str(uuid.uuid4())
    changes = [
        {
            "type": "update",
            "table": "notifications",
            "current_row_data": {
                "service_id": service_id,
                "template_id": template_id,
                "notification_type": "sms",
                "notification_status": "sending",
            },
            "previous_row_data": {
                "id": str(uuid.uuid4()),
            },
        }
    ]

    mocker.patch("app.celery.process_replication_slot_changes.get_replication_changes", return_value=changes)
    mock_commit = mocker.patch("app.celery.process_replication_slot_changes.db.session.commit")
    mock_apply_insert = mocker.patch("app.celery.process_replication_slot_changes.apply_service_stats_insert")
    mock_apply_update = mocker.patch("app.celery.process_replication_slot_changes.apply_service_stats_update_transition")

    check_replication_slot_changes()

    mock_apply_update.assert_not_called()
    mock_apply_insert.assert_called_once()
    dimensions = mock_apply_insert.call_args.args[0]
    assert dimensions["notification_status"] == "sending"
    assert str(dimensions["service_id"]) == service_id
    assert str(dimensions["template_id"]) == template_id
    assert dimensions["notification_type"] == "sms"
    mock_commit.assert_called_once()


def test_check_replication_slot_changes_processes_user_payload_shape(mocker):
    service_id = str(uuid.uuid4())
    template_id = str(uuid.uuid4())
    notification_id = str(uuid.uuid4())
    changes = [
        {
            "type": "insert",
            "table": "notifications",
            "current_row_data": {
                "id": notification_id,
                "service_id": service_id,
                "template_id": template_id,
                "notification_type": "sms",
                "notification_status": "created",
                "billable_units": 0,
            },
            "previous_row_data": {},
        },
        {
            "type": "update",
            "table": "notifications",
            "current_row_data": {
                "id": notification_id,
                "service_id": service_id,
                "template_id": template_id,
                "notification_type": "sms",
                "notification_status": "sending",
                "billable_units": 1,
            },
            "previous_row_data": {
                "id": notification_id,
                "notification_status": "created",
            },
        },
    ]

    mocker.patch("app.celery.process_replication_slot_changes.get_replication_changes", return_value=changes)
    mock_commit = mocker.patch("app.celery.process_replication_slot_changes.db.session.commit")
    mock_apply_insert = mocker.patch("app.celery.process_replication_slot_changes.apply_service_stats_insert")
    mock_apply_update = mocker.patch("app.celery.process_replication_slot_changes.apply_service_stats_update_transition")

    check_replication_slot_changes()

    assert mock_apply_insert.call_count == 1
    assert mock_apply_update.call_count == 1

    inserted_dimensions = mock_apply_insert.call_args.args[0]
    assert str(inserted_dimensions["service_id"]) == service_id
    assert str(inserted_dimensions["template_id"]) == template_id
    assert inserted_dimensions["notification_type"] == "sms"
    assert inserted_dimensions["notification_status"] == "created"

    old_dimensions, new_dimensions = mock_apply_update.call_args.args
    assert str(old_dimensions["service_id"]) == service_id
    assert str(old_dimensions["template_id"]) == template_id
    assert old_dimensions["notification_type"] == "sms"
    assert old_dimensions["notification_status"] == "created"
    assert str(new_dimensions["service_id"]) == service_id
    assert str(new_dimensions["template_id"]) == template_id
    assert new_dimensions["notification_type"] == "sms"
    assert new_dimensions["notification_status"] == "sending"

    mock_commit.assert_called_once()
