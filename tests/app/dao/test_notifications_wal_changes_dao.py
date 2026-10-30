import pytest
from flask import Flask

from app.dao.notifications_wal_changes_dao import (
    _get_replication_changes,
    dao_process_notifications_replication_slot_changes,
)


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
    assert result == {"lock_acquired": False, "slot_name": "notify_wal2json_slot", "upto_nchanges": 10000}


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
            "nextlsn": "0/AA",
            "lsn": "0/AA",
        },
        {
            "table": "notifications",
            "type": "update",
            "current_row_data": {},
            "previous_row_data": {},
            "nextlsn": "0/BB",
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
