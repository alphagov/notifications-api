import json
from collections import Counter
from datetime import date
from typing import Any

import pytest
from flask import Flask
from notifications_utils.testing.comparisons import AnySupersetOf

from app.dao import notifications_wal_changes_dao as dao
from app.dao.notifications_wal_changes_dao import (
    FullDimensions,
    LockNotAcquired,
    ProcessNotificationsReplicationSlotChangesResult,
    TableName,
    _build_change_counter,
    _BuildChangeCounterResult,
    dao_process_notifications_replication_slot_changes,
)


def _default_columns():
    return {
        "service_id": "550e8400-e29b-41d4-a716-446655440000",
        "template_id": "550e8400-e29b-41d4-a716-446655440001",
        "job_id": "550e8400-e29b-41d4-a716-446655440007",
        "notification_type": "email",
        "key_type": "normal",
        "notification_status": "delivered",
        "created_at": "2026-08-06T10:00:00Z",
        "uninteresting_column": "abc",
    }


def _default_identity():
    return {
        "notification_status": "pending",
        "irrelevant_column": "321",
    }


def _build_raw_change(
    *,
    action: str = "I",
    table: str | None = "notifications",
    schema: str | None = "public",
    columns: dict | None = None,
    identity: dict | None = None,
    transactional: bool | None = None,
) -> str:
    base: dict[str, Any] = {
        "action": action,
    }

    if table is not None and action in ("I", "U", "D", "T"):
        base["table"] = table

    if schema is not None and action in ("I", "U", "D", "T"):
        base["schema"] = schema

    if columns is None and action in ("I", "U"):
        columns = _default_columns()

    if columns is not None:
        base["columns"] = [{"name": k, "value": v} for k, v in columns.items()]

    if identity is None and action in ("U", "D"):
        identity = _default_identity()

    if identity is not None:
        base["identity"] = [{"name": k, "value": v} for k, v in identity.items()]

    if transactional is not None:
        base["transactional"] = transactional

    return json.dumps(base)


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
    mock_try_advisory_lock = mocker.patch(
        "app.dao.notifications_wal_changes_dao._try_advisory_lock",
        return_value=False,
    )
    # mock the two things we really want to ensure aren't called
    mock_advance = mocker.patch("app.dao.notifications_wal_changes_dao._advance_replication_slot")
    mock_upsert = mocker.patch("app.dao.notifications_wal_changes_dao._upsert_notification_status_live_count")

    with pytest.raises(LockNotAcquired):
        dao_process_notifications_replication_slot_changes(advisory_lock_id=4455)

    assert mock_try_advisory_lock.mock_calls == [mocker.call(4455)]

    assert not mock_advance.mock_calls
    assert not mock_upsert.mock_calls


_bccr = _BuildChangeCounterResult


@pytest.mark.parametrize(
    "raw_change_rows,expected_result",
    (
        (
            (
                ("0/AA", _build_raw_change()),
                ("0/BB", _build_raw_change(action="U")),
                ("0/DD", _build_raw_change(action="C", table=None, schema=None)),
            ),
            _bccr(
                change_counter=Counter(
                    {
                        FullDimensions(
                            date(2026, 8, 6),
                            "email",
                            "normal",
                            "delivered",
                            "550e8400-e29b-41d4-a716-446655440000",
                            "550e8400-e29b-41d4-a716-446655440001",
                            "550e8400-e29b-41d4-a716-446655440007",
                        ): 2,
                        FullDimensions(
                            date(2026, 8, 6),
                            "email",
                            "normal",
                            "pending",
                            "550e8400-e29b-41d4-a716-446655440000",
                            "550e8400-e29b-41d4-a716-446655440001",
                            "550e8400-e29b-41d4-a716-446655440007",
                        ): -1,
                    }
                ),
                advanceable_lsn="0/DD",
                raw_change_rows=3,
                counted_inserts=1,
                counted_updates=1,
                ignored_inserts=0,
                ignored_updates=0,
                ignored_deletes=0,
            ),
        ),
        (
            # works with single-use iterator
            iter(
                (
                    ("0/AA", _build_raw_change(action="U")),
                    ("0/BB", _build_raw_change(action="U")),
                    ("0/BC", _build_raw_change()),
                    ("0/D9", _build_raw_change(action="C", table=None, schema=None)),
                )
            ),
            _bccr(
                change_counter=Counter(
                    {
                        FullDimensions(
                            date(2026, 8, 6),
                            "email",
                            "normal",
                            "delivered",
                            "550e8400-e29b-41d4-a716-446655440000",
                            "550e8400-e29b-41d4-a716-446655440001",
                            "550e8400-e29b-41d4-a716-446655440007",
                        ): 3,
                        FullDimensions(
                            date(2026, 8, 6),
                            "email",
                            "normal",
                            "pending",
                            "550e8400-e29b-41d4-a716-446655440000",
                            "550e8400-e29b-41d4-a716-446655440001",
                            "550e8400-e29b-41d4-a716-446655440007",
                        ): -2,
                    }
                ),
                advanceable_lsn="0/D9",
                raw_change_rows=4,
                counted_inserts=1,
                counted_updates=2,
                ignored_inserts=0,
                ignored_updates=0,
                ignored_deletes=0,
            ),
        ),
        (
            # missing any commit
            (
                ("0/AA", _build_raw_change()),
                ("0/BB", _build_raw_change(action="U")),
            ),
            _bccr(
                change_counter=Counter(
                    {
                        FullDimensions(
                            date(2026, 8, 6),
                            "email",
                            "normal",
                            "delivered",
                            "550e8400-e29b-41d4-a716-446655440000",
                            "550e8400-e29b-41d4-a716-446655440001",
                            "550e8400-e29b-41d4-a716-446655440007",
                        ): 2,
                        FullDimensions(
                            date(2026, 8, 6),
                            "email",
                            "normal",
                            "pending",
                            "550e8400-e29b-41d4-a716-446655440000",
                            "550e8400-e29b-41d4-a716-446655440001",
                            "550e8400-e29b-41d4-a716-446655440007",
                        ): -1,
                    }
                ),
                advanceable_lsn=None,
                raw_change_rows=2,
                counted_inserts=1,
                counted_updates=1,
                ignored_inserts=0,
                ignored_updates=0,
                ignored_deletes=0,
            ),
        ),
        (
            # missing trailing commit
            (
                ("0/AA", _build_raw_change()),
                ("0/BB", _build_raw_change(action="C", table=None, schema=None)),
                ("0/CC", _build_raw_change(action="U")),
            ),
            _bccr(
                change_counter=Counter(
                    {
                        FullDimensions(
                            date(2026, 8, 6),
                            "email",
                            "normal",
                            "delivered",
                            "550e8400-e29b-41d4-a716-446655440000",
                            "550e8400-e29b-41d4-a716-446655440001",
                            "550e8400-e29b-41d4-a716-446655440007",
                        ): 2,
                        FullDimensions(
                            date(2026, 8, 6),
                            "email",
                            "normal",
                            "pending",
                            "550e8400-e29b-41d4-a716-446655440000",
                            "550e8400-e29b-41d4-a716-446655440001",
                            "550e8400-e29b-41d4-a716-446655440007",
                        ): -1,
                    }
                ),
                advanceable_lsn=None,
                raw_change_rows=3,
                counted_inserts=1,
                counted_updates=1,
                ignored_inserts=0,
                ignored_updates=0,
                ignored_deletes=0,
            ),
        ),
        (
            # only empty transactions
            (
                ("2/DD", _build_raw_change(action="B", table=None, schema=None)),
                ("2/E0", _build_raw_change(action="C", table=None, schema=None)),
                ("2/E1", _build_raw_change(action="B", table=None, schema=None)),
                ("2/E3", _build_raw_change(action="C", table=None, schema=None)),
                ("2/F0", _build_raw_change(action="B", table=None, schema=None)),
                ("2/F1", _build_raw_change(action="C", table=None, schema=None)),
            ),
            _bccr(
                change_counter=Counter(),
                advanceable_lsn="2/F1",
                raw_change_rows=6,
                counted_inserts=0,
                counted_updates=0,
                ignored_inserts=0,
                ignored_updates=0,
                ignored_deletes=0,
            ),
        ),
        (
            # sensible behaviour given empty changes
            (),
            _bccr(
                change_counter=Counter(),
                advanceable_lsn=None,
                raw_change_rows=0,
                counted_inserts=0,
                counted_updates=0,
                ignored_inserts=0,
                ignored_updates=0,
                ignored_deletes=0,
            ),
        ),
        (
            # across different tables
            (
                ("0/AA", _build_raw_change(columns=_default_columns() | {"job_id": None})),
                (
                    "0/BB",
                    _build_raw_change(
                        action="U",
                        columns=_default_columns() | {"job_id": None},
                        table="notification_history",
                    ),
                ),
                ("0/CC", _build_raw_change(action="U", table="notification_history")),
                ("0/DD", _build_raw_change(action="C", table=None, schema=None)),
                ("0/E0", _build_raw_change(action="B", table=None, schema=None)),
                ("0/E1", _build_raw_change(action="D")),
                ("0/FA", _build_raw_change(action="C", table=None, schema=None)),
            ),
            _bccr(
                change_counter=Counter(
                    {
                        FullDimensions(
                            date(2026, 8, 6),
                            "email",
                            "normal",
                            "delivered",
                            "550e8400-e29b-41d4-a716-446655440000",
                            "550e8400-e29b-41d4-a716-446655440001",
                            "550e8400-e29b-41d4-a716-446655440007",
                        ): 1,
                        FullDimensions(
                            date(2026, 8, 6),
                            "email",
                            "normal",
                            "pending",
                            "550e8400-e29b-41d4-a716-446655440000",
                            "550e8400-e29b-41d4-a716-446655440001",
                            "550e8400-e29b-41d4-a716-446655440007",
                        ): -1,
                        FullDimensions(
                            date(2026, 8, 6),
                            "email",
                            "normal",
                            "pending",
                            "550e8400-e29b-41d4-a716-446655440000",
                            "550e8400-e29b-41d4-a716-446655440001",
                            "00000000-0000-0000-0000-000000000000",
                        ): -1,
                        FullDimensions(
                            date(2026, 8, 6),
                            "email",
                            "normal",
                            "delivered",
                            "550e8400-e29b-41d4-a716-446655440000",
                            "550e8400-e29b-41d4-a716-446655440001",
                            "00000000-0000-0000-0000-000000000000",
                        ): 2,
                    }
                ),
                advanceable_lsn="0/FA",
                raw_change_rows=7,
                counted_inserts=1,
                counted_updates=2,
                ignored_inserts=0,
                ignored_updates=0,
                ignored_deletes=1,
            ),
        ),
        (
            # ignore updates with unchanged identity columns
            (
                ("0/01", _build_raw_change(action="B", table=None, schema=None)),
                ("0/AA", _build_raw_change()),
                ("0/AE", _build_raw_change(action="C", table=None, schema=None)),
                ("0/AF", _build_raw_change(action="B", table=None, schema=None)),
                (
                    "0/BB",
                    _build_raw_change(action="U", identity=_default_identity() | {"notification_status": "delivered"}),
                ),
                (
                    "0/BF",
                    _build_raw_change(
                        action="U",
                        columns=_default_columns() | {"job_id": None},  # key shouldn't even appear in counter
                        identity=_default_identity() | {"notification_status": "delivered"},
                    ),
                ),
                ("0/DD", _build_raw_change(action="C", table=None, schema=None)),
            ),
            _bccr(
                change_counter=Counter(
                    {
                        FullDimensions(
                            date(2026, 8, 6),
                            "email",
                            "normal",
                            "delivered",
                            "550e8400-e29b-41d4-a716-446655440000",
                            "550e8400-e29b-41d4-a716-446655440001",
                            "550e8400-e29b-41d4-a716-446655440007",
                        ): 1,
                    }
                ),
                advanceable_lsn="0/DD",
                raw_change_rows=7,
                counted_inserts=1,
                counted_updates=0,
                ignored_inserts=0,
                ignored_updates=2,
                ignored_deletes=0,
            ),
        ),
        (
            # daylight savings time
            (
                ("9/110", _build_raw_change(columns=_default_columns() | {"created_at": "2025-07-07T00:12:34Z"})),
                (
                    "9/120",
                    _build_raw_change(action="U", columns=_default_columns() | {"created_at": "2025-07-07T01:12:34Z"}),
                ),
                (
                    "9/121",
                    _build_raw_change(action="U", columns=_default_columns() | {"created_at": "2025-07-06T23:45:12Z"}),
                ),
                (
                    "9/220",
                    _build_raw_change(
                        action="U",
                        identity=_default_identity() | {"notification_status": "permanent-failure"},
                        columns=_default_columns() | {"created_at": "2025-07-06T22:45:12Z"},
                    ),
                ),
                ("9/222", _build_raw_change(action="C", table=None, schema=None)),
                (
                    "9/323",
                    _build_raw_change(
                        action="U",
                        table="notification_history",
                        columns=_default_columns() | {"created_at": "2025-07-07T01:45:12Z"},
                    ),
                ),
                ("9/333", _build_raw_change(action="I", schema="foo")),  # ignored due to schema
                (
                    "9/334",
                    _build_raw_change(
                        action="I", columns=_default_columns() | {"key_type": "foo"}
                    ),  # ignored due to key_type
                ),
                ("9/622", _build_raw_change(action="C", table=None, schema=None)),
            ),
            _bccr(
                change_counter=Counter(
                    {
                        FullDimensions(
                            date(2025, 7, 7),
                            "email",
                            "normal",
                            "delivered",
                            "550e8400-e29b-41d4-a716-446655440000",
                            "550e8400-e29b-41d4-a716-446655440001",
                            "550e8400-e29b-41d4-a716-446655440007",
                        ): 4,
                        FullDimensions(
                            date(2025, 7, 7),
                            "email",
                            "normal",
                            "pending",
                            "550e8400-e29b-41d4-a716-446655440000",
                            "550e8400-e29b-41d4-a716-446655440001",
                            "550e8400-e29b-41d4-a716-446655440007",
                        ): -3,
                        FullDimensions(
                            date(2025, 7, 6),
                            "email",
                            "normal",
                            "delivered",
                            "550e8400-e29b-41d4-a716-446655440000",
                            "550e8400-e29b-41d4-a716-446655440001",
                            "550e8400-e29b-41d4-a716-446655440007",
                        ): 1,
                        FullDimensions(
                            date(2025, 7, 6),
                            "email",
                            "normal",
                            "permanent-failure",
                            "550e8400-e29b-41d4-a716-446655440000",
                            "550e8400-e29b-41d4-a716-446655440001",
                            "550e8400-e29b-41d4-a716-446655440007",
                        ): -1,
                    }
                ),
                advanceable_lsn="9/622",
                raw_change_rows=9,
                counted_inserts=1,
                counted_updates=4,
                ignored_inserts=2,
                ignored_updates=0,
                ignored_deletes=0,
            ),
        ),
        (
            # most changes ignored for various reasons
            (
                ("0/A0", _build_raw_change(columns=_default_columns() | {"notification_type": "sms"})),
                ("0/A1", _build_raw_change(columns=_default_columns() | {"key_type": "test"})),
                ("0/B0", _build_raw_change(action="D", table="foo", schema="bar")),
                ("0/B1", _build_raw_change(action="U", columns=_default_columns() | {"notification_type": "letter"})),
                ("0/B2", _build_raw_change(action="U", columns=_default_columns() | {"key_type": "test"})),
                ("0/DD", _build_raw_change(action="C", table=None, schema=None)),
                ("0/DE", _build_raw_change(action="B", table=None, schema=None)),
                (
                    "0/E0",
                    _build_raw_change(
                        action="I",
                        table="notification_history",
                        columns=_default_columns() | {"notification_status": "created"},
                    ),
                ),
                ("0/E5", _build_raw_change(action="C", table=None, schema=None)),
            ),
            _bccr(
                change_counter=Counter(
                    {
                        FullDimensions(
                            date(2026, 8, 6),
                            "letter",
                            "normal",
                            "delivered",
                            "550e8400-e29b-41d4-a716-446655440000",
                            "550e8400-e29b-41d4-a716-446655440001",
                            "550e8400-e29b-41d4-a716-446655440007",
                        ): 1,
                        FullDimensions(
                            date(2026, 8, 6),
                            "letter",
                            "normal",
                            "pending",
                            "550e8400-e29b-41d4-a716-446655440000",
                            "550e8400-e29b-41d4-a716-446655440001",
                            "550e8400-e29b-41d4-a716-446655440007",
                        ): -1,
                        FullDimensions(
                            date(2026, 8, 6),
                            "sms",
                            "normal",
                            "delivered",
                            "550e8400-e29b-41d4-a716-446655440000",
                            "550e8400-e29b-41d4-a716-446655440001",
                            "550e8400-e29b-41d4-a716-446655440007",
                        ): 1,
                    }
                ),
                advanceable_lsn="0/E5",
                raw_change_rows=9,
                counted_inserts=1,
                counted_updates=1,
                ignored_inserts=2,
                ignored_updates=1,
                ignored_deletes=1,
            ),
        ),
        (
            # missing final commit - doesn't use lsn of transactional message
            (
                ("0/01", _build_raw_change(action="B", table=None, schema=None)),
                ("0/AA", _build_raw_change()),
                ("0/BB", _build_raw_change(action="M", transactional=True, table=None, schema=None)),
            ),
            _bccr(
                change_counter=Counter(
                    {
                        FullDimensions(
                            date(2026, 8, 6),
                            "email",
                            "normal",
                            "delivered",
                            "550e8400-e29b-41d4-a716-446655440000",
                            "550e8400-e29b-41d4-a716-446655440001",
                            "550e8400-e29b-41d4-a716-446655440007",
                        ): 1,
                    }
                ),
                advanceable_lsn=None,
                raw_change_rows=3,
                counted_inserts=1,
                counted_updates=0,
                ignored_inserts=0,
                ignored_updates=0,
                ignored_deletes=0,
            ),
        ),
        (
            # uses lsn of trailing non-transactional message
            (
                ("0/03", _build_raw_change(action="M", transactional=False, table=None, schema=None)),
                ("0/05", _build_raw_change(action="B", table=None, schema=None)),
                (
                    "0/AA",
                    _build_raw_change(
                        action="U", table="notification_history", columns=_default_columns() | {"job_id": None}
                    ),
                ),
                ("0/AB", _build_raw_change()),
                ("0/AE", _build_raw_change(action="D")),
                ("0/AF", _build_raw_change(action="C", table=None, schema=None)),
                ("1/BB", _build_raw_change(action="M", transactional=False, table=None, schema=None)),
            ),
            _bccr(
                change_counter=Counter(
                    {
                        FullDimensions(
                            date(2026, 8, 6),
                            "email",
                            "normal",
                            "delivered",
                            "550e8400-e29b-41d4-a716-446655440000",
                            "550e8400-e29b-41d4-a716-446655440001",
                            "550e8400-e29b-41d4-a716-446655440007",
                        ): 1,
                        FullDimensions(
                            date(2026, 8, 6),
                            "email",
                            "normal",
                            "delivered",
                            "550e8400-e29b-41d4-a716-446655440000",
                            "550e8400-e29b-41d4-a716-446655440001",
                            "00000000-0000-0000-0000-000000000000",
                        ): 1,
                        FullDimensions(
                            date(2026, 8, 6),
                            "email",
                            "normal",
                            "pending",
                            "550e8400-e29b-41d4-a716-446655440000",
                            "550e8400-e29b-41d4-a716-446655440001",
                            "00000000-0000-0000-0000-000000000000",
                        ): -1,
                    }
                ),
                advanceable_lsn="1/BB",
                raw_change_rows=7,
                counted_inserts=1,
                counted_updates=1,
                ignored_inserts=0,
                ignored_updates=0,
                ignored_deletes=1,
            ),
        ),
    ),
)
def test_build_change_counter(raw_change_rows, expected_result):
    assert _build_change_counter(raw_change_rows) == expected_result


def test_build_change_counter_skips_logs_empty_payloads(caplog):
    raw_change_rows = [
        ("0/AA", _build_raw_change()),
        ("0/BB", _build_raw_change(action="U")),
        ("0/CC", None),
        ("0/DD", _build_raw_change(action="C", table=None, schema=None)),
    ]

    result = _build_change_counter(raw_change_rows)

    assert result.change_counter == {
        (
            date(2026, 8, 6),
            "email",
            "normal",
            "delivered",
            "550e8400-e29b-41d4-a716-446655440000",
            "550e8400-e29b-41d4-a716-446655440001",
            "550e8400-e29b-41d4-a716-446655440007",
        ): 2,
        (
            date(2026, 8, 6),
            "email",
            "normal",
            "pending",
            "550e8400-e29b-41d4-a716-446655440000",
            "550e8400-e29b-41d4-a716-446655440001",
            "550e8400-e29b-41d4-a716-446655440007",
        ): -1,
    }
    assert result.advanceable_lsn == "0/DD"
    assert "Encountered None replication payload" in caplog.messages


def test_build_change_counter_skips_logs_empty_lsns(caplog):
    raw_change_rows = [
        ("0/AA", _build_raw_change()),
        ("0/BB", _build_raw_change(action="U")),
        (None, _build_raw_change(action="B", table=None, schema=None)),
        ("0/DD", _build_raw_change(action="C", table=None, schema=None)),
    ]

    result = _build_change_counter(raw_change_rows)

    assert result.change_counter == {
        (
            date(2026, 8, 6),
            "email",
            "normal",
            "delivered",
            "550e8400-e29b-41d4-a716-446655440000",
            "550e8400-e29b-41d4-a716-446655440001",
            "550e8400-e29b-41d4-a716-446655440007",
        ): 2,
        (
            date(2026, 8, 6),
            "email",
            "normal",
            "pending",
            "550e8400-e29b-41d4-a716-446655440000",
            "550e8400-e29b-41d4-a716-446655440001",
            "550e8400-e29b-41d4-a716-446655440007",
        ): -1,
    }
    assert result.advanceable_lsn == "0/DD"
    assert "Encountered None replication lsn" in caplog.messages


def test_peek_call_uses_expected_arguments(mocker):
    mocker.patch("app.dao.notifications_wal_changes_dao._try_advisory_lock", return_value=True)
    mock_execute = mocker.patch(
        "app.dao.notifications_wal_changes_dao.db.session.execute",
        # no point in progressing past this point
        side_effect=RuntimeError("That's enough"),
    )

    with pytest.raises(RuntimeError, match="That's enough"):
        dao_process_notifications_replication_slot_changes(
            slot_name="slotty",
            upto_nchanges=201,
            insert_table_names={TableName("public", "foo"), TableName("public", "bar")},
            update_table_names={TableName("public", "foo"), TableName("special", "foo")},
        )

    peek_execute_call = mock_execute.mock_calls[0]
    assert "pg_logical_slot_peek_changes" in str(peek_execute_call.args[0])  # ensure we've got the right call

    assert peek_execute_call.args[1] == AnySupersetOf(
        {
            "slot_name": "slotty",
            "upto_nchanges": 201,
            "include_lsn": "false",
            "format_version": "2",
            "include_types": "false",
            "include_typmod": "false",
        }
    )

    assert sorted(s.strip() for s in peek_execute_call.args[1]["table_names"].split(",")) == [
        "public.bar",
        "public.foo",
        "special.foo",
    ]


def test_raises_if_changes_but_no_lsn_returned_by_build_change_counter(mocker):
    mocker.patch("app.dao.notifications_wal_changes_dao._try_advisory_lock", return_value=True)
    mocker.patch("app.dao.notifications_wal_changes_dao._advisory_unlock")
    mock_upsert = mocker.patch("app.dao.notifications_wal_changes_dao._upsert_notification_status_live_count")
    mock_advance = mocker.patch("app.dao.notifications_wal_changes_dao._advance_replication_slot")
    mock_rollback = mocker.patch("app.dao.notifications_wal_changes_dao.db.session.rollback")
    mocker.patch(
        "app.dao.notifications_wal_changes_dao._get_raw_replication_change_rows",
        return_value=((None, _build_raw_change()),),
    )

    with pytest.raises(
        ValueError,
        match=r"No advanceable_lsn found .* replication slot notify_wal2json_slot will not be advanced",
    ):
        dao_process_notifications_replication_slot_changes(advisory_lock_id=77)

    assert mock_rollback.mock_calls == [mocker.call()]
    assert not mock_upsert.mock_calls
    assert not mock_advance.mock_calls


def test_does_not_raise_when_no_changes_or_lsn_returned(mocker):
    mocker.patch("app.dao.notifications_wal_changes_dao._try_advisory_lock", return_value=True)
    mocker.patch("app.dao.notifications_wal_changes_dao._advisory_unlock")
    mocker.patch("app.dao.notifications_wal_changes_dao.db.session.rollback")
    mocker.patch("app.dao.notifications_wal_changes_dao._get_raw_replication_change_rows", return_value=())

    result = dao_process_notifications_replication_slot_changes(advisory_lock_id=77)

    assert result == ProcessNotificationsReplicationSlotChangesResult(
        change_count_buckets=0,
        advanced_to_lsn=None,
        raw_change_rows=0,
        counted_inserts=0,
        counted_updates=0,
        ignored_inserts=0,
        ignored_updates=0,
        ignored_deletes=0,
        applied_upserts=0,
    )


def test_upsert_notification_status_live_count_batches_non_zero_changes(mocker):
    mock_upsert = mocker.patch("app.dao.notifications_wal_changes_dao.upsert_notification_status_live_counts")

    service_id = "550e8400-e29b-41d4-a716-446655440000"
    template_id = "550e8400-e29b-41d4-a716-446655440001"
    job_id = "550e8400-e29b-41d4-a716-446655440002"
    dao._upsert_notification_status_live_count(
        {
            FullDimensions(
                date(2026, 8, 6),
                "sms",
                "normal",
                "delivered",
                service_id,
                template_id,
                job_id,
            ): 2,
            FullDimensions(
                date(2026, 8, 6),
                "sms",
                "normal",
                "failed",
                service_id,
                template_id,
                job_id,
            ): -1,
            FullDimensions(
                date(2026, 8, 6),
                "sms",
                "normal",
                "created",
                service_id,
                template_id,
                job_id,
            ): 0,
        }
    )

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
        "app.dao.notifications_wal_changes_dao._get_raw_replication_change_rows",
        return_value=(
            ("0/01", _build_raw_change()),
            ("0/02", _build_raw_change()),
            ("0/FF", _build_raw_change(action="C", table=None, schema=None)),
        ),
    )
    manager.attach_mock(
        mocker.patch("app.dao.notifications_wal_changes_dao._upsert_notification_status_live_count"), "upsert"
    )
    manager.attach_mock(mocker.patch("app.dao.notifications_wal_changes_dao._advance_replication_slot"), "advance")

    with Flask(__name__).app_context():
        dao_process_notifications_replication_slot_changes(slot_name="slotty", advisory_lock_id=77)

    # The slot must only advance once the counts have been written
    assert manager.mock_calls == [
        mocker.call.upsert(
            {
                (
                    date(2026, 8, 6),
                    "email",
                    "normal",
                    "delivered",
                    "550e8400-e29b-41d4-a716-446655440000",
                    "550e8400-e29b-41d4-a716-446655440001",
                    "550e8400-e29b-41d4-a716-446655440007",
                ): 2,
            }
        ),
        mocker.call.advance("0/FF", slot_name="slotty"),
    ]


def test_does_not_advance_replication_slot_when_upsert_fails(mocker, caplog):
    mocker.patch("app.dao.notifications_wal_changes_dao._try_advisory_lock", return_value=True)
    mock_unlock = mocker.patch("app.dao.notifications_wal_changes_dao._advisory_unlock")
    mock_rollback = mocker.patch("app.dao.notifications_wal_changes_dao.db.session.rollback")
    mocker.patch(
        "app.dao.notifications_wal_changes_dao._get_raw_replication_change_rows",
        return_value=(
            (
                "0/01",
                _build_raw_change(
                    columns={
                        "service_id": "550e8400-e29b-41d4-a716-446655440000",
                        "template_id": "550e8400-e29b-41d4-a716-446655440001",
                        "job_id": "550e8400-e29b-41d4-a716-446655440002",
                        "notification_type": "sms",
                        "key_type": "normal",
                        "created_at": "2026-08-06T10:00:00Z",
                        "notification_status": "created",
                    }
                ),
            ),
            ("0/02", _build_raw_change(action="C", table=None, schema=None)),
        ),
    )
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


def test_advances_replication_slot_when_no_changes_but_with_lsn(mocker):
    mocker.patch("app.dao.notifications_wal_changes_dao._try_advisory_lock", return_value=True)
    mocker.patch("app.dao.notifications_wal_changes_dao._advisory_unlock")
    mocker.patch(
        "app.dao.notifications_wal_changes_dao._get_raw_replication_change_rows",
        return_value=(
            ("0/01", _build_raw_change(action="B", table=None, schema=None)),
            ("0/09", _build_raw_change(action="C", table=None, schema=None)),
        ),
    )
    mock_advance = mocker.patch("app.dao.notifications_wal_changes_dao._advance_replication_slot")

    with Flask(__name__).app_context():
        dao_process_notifications_replication_slot_changes(advisory_lock_id=77, slot_name="slotty")

    assert mock_advance.mock_calls == [mocker.call("0/09", slot_name="slotty")]


def test_does_not_advance_replication_slot_when_no_changes_no_lsn(mocker):
    mocker.patch("app.dao.notifications_wal_changes_dao._try_advisory_lock", return_value=True)
    mocker.patch("app.dao.notifications_wal_changes_dao._advisory_unlock")
    mocker.patch("app.dao.notifications_wal_changes_dao._get_raw_replication_change_rows", return_value=[])
    mock_advance = mocker.patch("app.dao.notifications_wal_changes_dao._advance_replication_slot")

    with Flask(__name__).app_context():
        dao_process_notifications_replication_slot_changes(advisory_lock_id=77, slot_name="slotty")

    assert not mock_advance.mock_calls


def test_rolls_back_session_when_processing_fails(mocker):
    mocker.patch("app.dao.notifications_wal_changes_dao._try_advisory_lock", return_value=True)
    mocker.patch("app.dao.notifications_wal_changes_dao._advisory_unlock")
    mocker.patch(
        "app.dao.notifications_wal_changes_dao._get_raw_replication_change_rows",
        side_effect=RuntimeError("query failed"),
    )
    mock_rollback = mocker.patch("app.dao.notifications_wal_changes_dao.db.session.rollback")

    with Flask(__name__).app_context(), pytest.raises(RuntimeError, match="query failed"):
        dao_process_notifications_replication_slot_changes(advisory_lock_id=77)

    mock_rollback.assert_called_once_with()


def test_returns_summary_of_processed_changes(mocker):
    mocker.patch("app.dao.notifications_wal_changes_dao._try_advisory_lock", return_value=True)
    mocker.patch("app.dao.notifications_wal_changes_dao._advisory_unlock")
    mocker.patch(
        "app.dao.notifications_wal_changes_dao._get_raw_replication_change_rows",
        return_value=(
            ("0/01", _build_raw_change()),
            ("0/02", _build_raw_change(action="U")),
            (
                "0/07",
                _build_raw_change(
                    table="notification_history",
                ),
            ),
            ("0/FF", _build_raw_change(action="C", table=None, schema=None)),
        ),
    )
    mocker.patch("app.dao.notifications_wal_changes_dao._upsert_notification_status_live_count", return_value=123)
    mocker.patch("app.dao.notifications_wal_changes_dao._advance_replication_slot")

    with Flask(__name__).app_context():
        result = dao_process_notifications_replication_slot_changes(advisory_lock_id=77)

    assert result == ProcessNotificationsReplicationSlotChangesResult(
        change_count_buckets=2,
        advanced_to_lsn="0/FF",
        raw_change_rows=4,
        counted_inserts=1,
        counted_updates=1,
        ignored_inserts=1,
        ignored_updates=0,
        ignored_deletes=0,
        applied_upserts=123,
    )


def test_ignores_inserts_on_notification_history_table(mocker):
    mocker.patch("app.dao.notifications_wal_changes_dao._try_advisory_lock", return_value=True)
    mocker.patch("app.dao.notifications_wal_changes_dao._advisory_unlock")
    mocker.patch(
        "app.dao.notifications_wal_changes_dao._get_raw_replication_change_rows",
        return_value=[
            (
                "0/01",
                _build_raw_change(
                    action="I",
                    identity={"status": "delivered"},
                    table="notification_history",
                ),
            ),
            (
                "0/02",
                _build_raw_change(
                    action="I",
                    identity={"status": "sent"},
                    table="notification_history",
                ),
            ),
            ("0/E5", _build_raw_change(action="C", table=None, schema=None)),
        ],
    )
    upsert = mocker.patch("app.dao.notifications_wal_changes_dao._upsert_notification_status_live_count")
    advance = mocker.patch("app.dao.notifications_wal_changes_dao._advance_replication_slot")

    with Flask(__name__).app_context():
        result = dao_process_notifications_replication_slot_changes(advisory_lock_id=77)

    assert result == ProcessNotificationsReplicationSlotChangesResult(
        change_count_buckets=0,
        advanced_to_lsn="0/E5",
        raw_change_rows=3,
        counted_inserts=0,
        counted_updates=0,
        ignored_inserts=2,
        ignored_updates=0,
        ignored_deletes=0,
        applied_upserts=0,
    )

    assert not upsert.mock_calls
    assert advance.mock_calls == [mocker.call("0/E5", slot_name=dao.REPLICATION_SLOT_NAME)]
