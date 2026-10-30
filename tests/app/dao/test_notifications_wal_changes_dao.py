import pytest
from flask import Flask

from app.dao.notifications_wal_changes_dao import dao_process_notifications_replication_slot_changes


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
