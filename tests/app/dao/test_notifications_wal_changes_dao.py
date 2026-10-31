from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from flask import Flask

from app.dao import notifications_wal_changes_dao as dao
from app.dao.notifications_wal_changes_dao import (
    _get_replication_changes,
    dao_process_notifications_replication_slot_changes,
)


def _build_change(
    *,
    table: str = "notifications",
    change_type: str = "insert",
    current_row_data: dict | None = None,
    previous_row_data: dict | None = None,
    lsn: str | None = None,
) -> dict:
    return {
        "table": table,
        "type": change_type,
        "current_row_data": current_row_data or {},
        "previous_row_data": previous_row_data or {},
        "lsn": lsn,
    }


def test_acquires_and_releases_advisory_lock(mocker):
    session = mocker.patch("app.dao.notifications_wal_changes_dao.db.session")
    session.execute.return_value.scalar.return_value = True
    lock_id = 123

    dao_process_notifications_replication_slot_changes(advisory_lock_id=lock_id)
    calls = session.execute.call_args_list

    # Check that the advisory lock was acquired first
    assert str(calls[0].args[0]) == "SELECT pg_try_advisory_lock(:lock_id)"
    assert calls[0].args[1] == {"lock_id": lock_id}

    # Check that the advisory lock was released last
    assert str(calls[-1].args[0]) == "SELECT pg_advisory_unlock(:lock_id)"
    assert calls[-1].args[1] == {"lock_id": lock_id}


def test_when_lock_acquisition_fails_returns_without_processing(mocker):
    mocker.patch(
        "app.dao.notifications_wal_changes_dao._try_advisory_lock",
        return_value=False,
    )

    result = dao_process_notifications_replication_slot_changes()
    assert result == {"lock_acquired": False, "slot_name": "notify_wal2json_slot"}


def test_when_lock_acquisition_fails(mocker, caplog):
    mocker.patch(
        "app.dao.notifications_wal_changes_dao._try_advisory_lock",
        side_effect=RuntimeError("lock failed"),
    )

    with Flask(__name__).app_context(), pytest.raises(RuntimeError, match="lock failed"):
        dao_process_notifications_replication_slot_changes()

    assert "Failed to process replication slot changes" in caplog.messages


def test_when_lock_acquisition_fails_logs(mocker, caplog):
    mocker.patch(
        "app.dao.notifications_wal_changes_dao._try_advisory_lock",
        side_effect=RuntimeError("lock failed"),
    )

    with Flask(__name__).app_context(), pytest.raises(RuntimeError, match="lock failed"):
        dao_process_notifications_replication_slot_changes()

    assert "Failed to process replication slot changes" in caplog.messages


def test_when_unlock_fails_logs(mocker, caplog):
    mocker.patch("app.dao.notifications_wal_changes_dao._try_advisory_lock", return_value=True)
    mocker.patch(
        "app.dao.notifications_wal_changes_dao._advisory_unlock",
        side_effect=RuntimeError("unlock failed"),
    )

    with Flask(__name__).app_context(), pytest.raises(RuntimeError, match="unlock failed"):
        dao_process_notifications_replication_slot_changes()

    assert "Failed to release advisory lock" in caplog.messages


def test_get_replication_changes_parses_rows_and_skips_empty_payloads(mocker):
    mappings_rows = [
        {"lsn": "0/AA", "data": '{"action": "I", "schema": "public", "table": "notifications"}'},
        {"lsn": "0/BB", "data": '{"action": "U", "schema": "public", "table": "notifications"}'},
        {"lsn": "0/CC", "data": None},
    ]
    execute_result = mocker.Mock()
    execute_result.mappings.return_value = mappings_rows
    mock_execute = mocker.patch("app.dao.notifications_wal_changes_dao.db.session.execute", return_value=execute_result)

    result, last_lsn = _get_replication_changes(slot_name="slot", upto_nchanges=20, table_name="public.notifications")

    assert result == [
        {
            "table": "notifications",
            "type": "insert",
            "current_row_data": {},
            "previous_row_data": {},
            "lsn": "0/AA",
        },
        {
            "table": "notifications",
            "type": "update",
            "current_row_data": {},
            "previous_row_data": {},
            "lsn": "0/BB",
        },
    ]
    assert last_lsn == "0/BB"
    mock_execute.assert_called_once()


def test_get_replication_changes_preserves_sql_lsn(mocker):
    mappings_rows = [{"lsn": "0/AB", "data": '{"action": "I", "schema": "public", "table": "notifications"}'}]
    execute_result = mocker.Mock()
    execute_result.mappings.return_value = mappings_rows
    mocker.patch("app.dao.notifications_wal_changes_dao.db.session.execute", return_value=execute_result)

    result, last_lsn = _get_replication_changes(slot_name="slot", upto_nchanges=20, table_name="public.notifications")

    assert result[0]["lsn"] == "0/AB"
    assert last_lsn == "0/AB"


def test_get_replication_changes_accepts_iterable_mappings(mocker):
    mappings_rows = [{"lsn": "0/AB", "data": '{"action": "I", "schema": "public", "table": "other"}'}]
    execute_result = mocker.Mock()
    execute_result.mappings.return_value = iter(mappings_rows)
    mocker.patch("app.dao.notifications_wal_changes_dao.db.session.execute", return_value=execute_result)

    result, last_lsn = _get_replication_changes(slot_name="slot", upto_nchanges=20, table_name="public.notifications")

    assert result == []
    assert last_lsn == "0/AB"


def test_get_replication_changes_uses_format_version_2(mocker):
    execute_result = mocker.Mock()
    execute_result.mappings.return_value = []
    mock_execute = mocker.patch("app.dao.notifications_wal_changes_dao.db.session.execute", return_value=execute_result)

    _get_replication_changes(slot_name="slot", upto_nchanges=20, table_name="public.notifications")

    mock_execute.assert_called_once()
    assert mock_execute.call_args.args[1]["format_version"] == "2"


def test_get_replication_changes_raises_if_no_lsn_returned(mocker):
    mocker.patch("app.dao.notifications_wal_changes_dao._try_advisory_lock", return_value=True)
    mocker.patch("app.dao.notifications_wal_changes_dao._advisory_unlock")
    mock_rollback = mocker.patch("app.dao.notifications_wal_changes_dao.db.session.rollback")
    mocker.patch(
        "app.dao.notifications_wal_changes_dao._get_replication_changes",
        return_value=([mocker.Mock()], None),
    )

    with pytest.raises(
        RuntimeError,
        match=r"No last_lsn found .* replication slot notify_wal2json_slot will not be advanced",
    ):
        dao_process_notifications_replication_slot_changes(advisory_lock_id=77)

    mock_rollback.assert_called_once_with()


def test_does_not_raise_when_no_changes_returned(mocker):
    mocker.patch("app.dao.notifications_wal_changes_dao._try_advisory_lock", return_value=True)
    mocker.patch("app.dao.notifications_wal_changes_dao._advisory_unlock")
    mocker.patch("app.dao.notifications_wal_changes_dao.db.session.rollback")
    mocker.patch(
        "app.dao.notifications_wal_changes_dao._get_replication_changes",
        return_value=([], None),
    )

    result = dao_process_notifications_replication_slot_changes(advisory_lock_id=77)

    assert result == {"lock_acquired": True, "slot_name": "notify_wal2json_slot", "changes_count": 0}


def test_parse_uuid_value():
    value = UUID("550e8400-e29b-41d4-a716-446655440000")

    assert dao._parse_uuid_value({"service_id": str(value)}, "service_id") == value
    assert dao._parse_uuid_value({"service_id": "not-a-uuid"}, "service_id") is None
    assert dao._parse_uuid_value({}, "service_id") is None


def test_get_str_value():
    assert dao._get_str_value({"value": "text"}, "value") == "text"
    assert dao._get_str_value({"value": 42}, "value") == "42"
    assert dao._get_str_value({"value": None}, "value") is None
    assert dao._get_str_value(None, "value") is None


def test_parse_datetime_value():
    assert dao._parse_datetime_value({"created_at": "2026-08-06T10:00:00Z"}, "created_at") == datetime(
        2026, 8, 6, 10, 0, 0, tzinfo=UTC
    )
    assert dao._parse_datetime_value({"created_at": "invalid"}, "created_at") is None
    assert dao._parse_datetime_value({}, "created_at") is None


def test_build_dimensions_returns_all_dimensions_and_converts_date(mocker):
    service_id = UUID("550e8400-e29b-41d4-a716-446655440000")
    template_id = UUID("550e8400-e29b-41d4-a716-446655440001")
    job_id = UUID("550e8400-e29b-41d4-a716-446655440002")
    created_at = datetime(2026, 8, 6, 10, 0, 0, tzinfo=UTC)
    mock_convert = mocker.patch("app.dao.notifications_wal_changes_dao.convert_utc_to_bst", return_value=created_at)
    change = _build_change(
        current_row_data={
            "service_id": str(service_id),
            "template_id": str(template_id),
            "job_id": str(job_id),
            "notification_type": "sms",
            "key_type": "normal",
            "notification_status": "delivered",
            "created_at": "2026-08-06T10:00:00Z",
        }
    )

    result = dao._build_dimensions(change, use_previous_row=False)

    assert result == (date(2026, 8, 6), service_id, template_id, job_id, "sms", "normal", "delivered")
    mock_convert.assert_called_once_with(created_at)


def test_build_dimensions_uses_fallback_row_when_primary_is_missing(mocker):
    service_id = UUID("550e8400-e29b-41d4-a716-446655440000")
    template_id = UUID("550e8400-e29b-41d4-a716-446655440001")
    job_id = UUID("550e8400-e29b-41d4-a716-446655440002")
    mocker.patch(
        "app.dao.notifications_wal_changes_dao.convert_utc_to_bst",
        return_value=datetime(2026, 8, 7, tzinfo=UTC),
    )
    change = _build_change(
        previous_row_data={
            "service_id": str(service_id),
            "template_id": str(template_id),
            "job_id": str(job_id),
            "notification_type": "email",
            "key_type": "normal",
            "notification_status": "failed",
            "created_at": "2026-08-07T00:00:00Z",
        }
    )

    result = dao._build_dimensions(change, use_previous_row=False)

    assert result == (date(2026, 8, 7), service_id, template_id, job_id, "email", "normal", "failed")


def test_build_dimensions_requires_status_in_previous_row_when_requested(mocker):
    mocker.patch(
        "app.dao.notifications_wal_changes_dao.convert_utc_to_bst",
        return_value=datetime(2026, 8, 7, tzinfo=UTC),
    )
    change = _build_change(
        current_row_data={"notification_status": "delivered"},
        previous_row_data={
            "service_id": "550e8400-e29b-41d4-a716-446655440000",
            "template_id": "550e8400-e29b-41d4-a716-446655440001",
            "job_id": "550e8400-e29b-41d4-a716-446655440002",
            "notification_type": "email",
            "key_type": "normal",
            "created_at": "2026-08-07T00:00:00Z",
        },
    )

    result = dao._build_dimensions(change, use_previous_row=True, require_status_from_primary_row=True)

    assert result is None


def test_build_dimensions_returns_none_when_required_fields_are_missing():
    change = _build_change(current_row_data={"key_type": "normal"})

    assert dao._build_dimensions(change, use_previous_row=False) is None


def test_build_dimensions_uses_zero_uuid_when_job_id_is_missing(mocker):
    mocker.patch(
        "app.dao.notifications_wal_changes_dao.convert_utc_to_bst",
        return_value=datetime(2026, 8, 7, tzinfo=UTC),
    )
    change = _build_change(
        current_row_data={
            "service_id": "550e8400-e29b-41d4-a716-446655440000",
            "template_id": "550e8400-e29b-41d4-a716-446655440001",
            "notification_type": "email",
            "key_type": "normal",
            "notification_status": "delivered",
            "created_at": "2026-08-07T00:00:00Z",
        }
    )

    result = dao._build_dimensions(change, use_previous_row=False)

    assert result is not None
    assert result.job_id == dao.NO_JOB_ID


def test_build_counter_from_changes_counts_inserts_and_status_transitions(mocker):
    mocker.patch(
        "app.dao.notifications_wal_changes_dao.convert_utc_to_bst",
        return_value=datetime(2026, 8, 6, tzinfo=UTC),
    )
    base = {
        "service_id": "550e8400-e29b-41d4-a716-446655440000",
        "template_id": "550e8400-e29b-41d4-a716-446655440001",
        "job_id": "550e8400-e29b-41d4-a716-446655440002",
        "notification_type": "sms",
        "key_type": "normal",
        "created_at": "2026-08-06T10:00:00Z",
    }
    changes = [
        _build_change(current_row_data={**base, "notification_status": "created"}, lsn="0/01"),
        _build_change(
            change_type="update",
            current_row_data={**base, "notification_status": "delivered"},
            previous_row_data={**base, "notification_status": "created"},
            lsn="0/02",
        ),
        _build_change(table="other", current_row_data={**base, "notification_status": "created"}, lsn="0/03"),
        _build_change(change_type="delete", current_row_data={**base, "notification_status": "created"}, lsn="0/04"),
    ]

    counter, processed_changes, ignored_changes = dao._build_counter_from_changes(changes)

    created_dimensions = dao._build_dimensions(changes[0], use_previous_row=False)
    delivered_dimensions = dao._build_dimensions(changes[1], use_previous_row=False)
    assert counter[created_dimensions] == 0
    assert counter[delivered_dimensions] == 1
    assert processed_changes == 2
    assert ignored_changes == 2


def test_build_counter_does_not_subtract_new_status_when_previous_status_is_missing(mocker):
    mocker.patch(
        "app.dao.notifications_wal_changes_dao.convert_utc_to_bst",
        return_value=datetime(2026, 8, 6, tzinfo=UTC),
    )
    base = {
        "service_id": "550e8400-e29b-41d4-a716-446655440000",
        "template_id": "550e8400-e29b-41d4-a716-446655440001",
        "job_id": "550e8400-e29b-41d4-a716-446655440002",
        "notification_type": "sms",
        "key_type": "normal",
        "created_at": "2026-08-06T10:00:00Z",
    }
    change = _build_change(
        change_type="update",
        current_row_data={**base, "notification_status": "delivered"},
        previous_row_data=base,
    )

    counter, processed_changes, ignored_changes = dao._build_counter_from_changes([change])

    delivered_dimensions = dao._build_dimensions(change, use_previous_row=False)
    assert counter[delivered_dimensions] == 1
    assert processed_changes == 1
    assert ignored_changes == 0


def test_upsert_notification_status_live_count_batches_non_zero_changes(mocker):
    service_id = UUID("550e8400-e29b-41d4-a716-446655440000")
    template_id = UUID("550e8400-e29b-41d4-a716-446655440001")
    job_id = UUID("550e8400-e29b-41d4-a716-446655440002")
    dimensions = (date(2026, 8, 6), service_id, template_id, job_id, "sms", "normal", "delivered")
    failed_dimensions = (date(2026, 8, 6), service_id, template_id, job_id, "sms", "normal", "failed")
    mock_upsert = mocker.patch("app.dao.notifications_wal_changes_dao.upsert_notification_status_live_counts")

    dao._upsert_notification_status_live_count({dimensions: 2, failed_dimensions: -1, (*dimensions[:-1], "created"): 0})

    mock_upsert.assert_called_once_with(
        [
            {
                "bst_date": date(2026, 8, 6),
                "service_id": service_id,
                "template_id": template_id,
                "job_id": job_id,
                "notification_type": "sms",
                "key_type": "normal",
                "notification_status": "delivered",
                "notification_count": 2,
            },
            {
                "bst_date": date(2026, 8, 6),
                "service_id": service_id,
                "template_id": template_id,
                "job_id": job_id,
                "notification_type": "sms",
                "key_type": "normal",
                "notification_status": "failed",
                "notification_count": -1,
            },
        ]
    )


def test_does_not_call_upsert_notification_status_live_count_when_no_changes(mocker):
    mock_upsert = mocker.patch("app.dao.notifications_wal_changes_dao.upsert_notification_status_live_counts")

    dao._upsert_notification_status_live_count({})

    mock_upsert.assert_not_called()


def test_advance_replication_slot_executes_slot_advance_sql(mocker):
    mock_execute = mocker.patch("app.dao.notifications_wal_changes_dao.db.session.execute")

    dao._advance_replication_slot("0/AB", slot_name="slot")

    mock_execute.assert_called_once()
    assert str(mock_execute.call_args.args[0]) == "SELECT pg_replication_slot_advance(:slot_name, :lsn)"
    assert mock_execute.call_args.args[1] == {"slot_name": "slot", "lsn": "0/AB"}


def test_advances_replication_slot_to_batch_last_lsn_after_upserting_counts(mocker):
    manager = mocker.Mock()
    mocker.patch("app.dao.notifications_wal_changes_dao._try_advisory_lock", return_value=True)
    mocker.patch("app.dao.notifications_wal_changes_dao._advisory_unlock")
    mocker.patch(
        "app.dao.notifications_wal_changes_dao._get_replication_changes",
        return_value=([_build_change(lsn="0/01"), _build_change(lsn="0/02")], "0/FF"),
    )
    counter = {"dimensions": 1}
    mocker.patch(
        "app.dao.notifications_wal_changes_dao._build_counter_from_changes",
        return_value=(counter, 2, 0),
    )
    manager.attach_mock(
        mocker.patch("app.dao.notifications_wal_changes_dao._upsert_notification_status_live_count"), "upsert"
    )
    manager.attach_mock(mocker.patch("app.dao.notifications_wal_changes_dao._advance_replication_slot"), "advance")

    with Flask(__name__).app_context():
        dao_process_notifications_replication_slot_changes(slot_name="slot", advisory_lock_id=77)

    # The slot must only advance once the counts have been written
    assert manager.mock_calls == [mocker.call.upsert(counter), mocker.call.advance("0/FF", slot_name="slot")]


def test_does_not_advance_replication_slot_when_upsert_fails(mocker, caplog):
    mocker.patch("app.dao.notifications_wal_changes_dao._try_advisory_lock", return_value=True)
    mock_unlock = mocker.patch("app.dao.notifications_wal_changes_dao._advisory_unlock")
    mock_rollback = mocker.patch("app.dao.notifications_wal_changes_dao.db.session.rollback")
    mocker.patch(
        "app.dao.notifications_wal_changes_dao._get_replication_changes",
        return_value=([_build_change(lsn="0/01")], "0/01"),
    )
    mocker.patch("app.dao.notifications_wal_changes_dao._build_counter_from_changes", return_value=({}, 1, 0))
    mocker.patch(
        "app.dao.notifications_wal_changes_dao._upsert_notification_status_live_count",
        side_effect=RuntimeError("upsert failed"),
    )
    mock_advance = mocker.patch("app.dao.notifications_wal_changes_dao._advance_replication_slot")

    with Flask(__name__).app_context(), pytest.raises(RuntimeError, match="upsert failed"):
        dao_process_notifications_replication_slot_changes(advisory_lock_id=77)

    mock_advance.assert_not_called()
    mock_unlock.assert_called_once_with(77)
    mock_rollback.assert_called_once_with()
    assert "Failed to process replication slot changes" in caplog.messages


def test_does_not_advance_replication_slot_when_no_changes(mocker):
    mocker.patch("app.dao.notifications_wal_changes_dao._try_advisory_lock", return_value=True)
    mocker.patch("app.dao.notifications_wal_changes_dao._advisory_unlock")
    mocker.patch("app.dao.notifications_wal_changes_dao._get_replication_changes", return_value=([], "0/01"))
    mock_advance = mocker.patch("app.dao.notifications_wal_changes_dao._advance_replication_slot")

    with Flask(__name__).app_context():
        dao_process_notifications_replication_slot_changes(advisory_lock_id=77)

    mock_advance.assert_not_called()


def test_rolls_back_session_when_processing_fails(mocker):
    mocker.patch("app.dao.notifications_wal_changes_dao._try_advisory_lock", return_value=True)
    mocker.patch("app.dao.notifications_wal_changes_dao._advisory_unlock")
    mocker.patch(
        "app.dao.notifications_wal_changes_dao._get_replication_changes",
        side_effect=RuntimeError("query failed"),
    )
    mock_rollback = mocker.patch("app.dao.notifications_wal_changes_dao.db.session.rollback")

    with Flask(__name__).app_context(), pytest.raises(RuntimeError, match="query failed"):
        dao_process_notifications_replication_slot_changes(advisory_lock_id=77)

    mock_rollback.assert_called_once_with()
