# total=False to make all keys optional by default, except those marked as Required
import struct
from typing import Required, TypedDict
import json
from flask import current_app
from sqlalchemy import text  # type: ignore[reportMissingImports]
from app import db

REPLICATION_SLOT_NAME = "notify_wal2json_slot"
REPLICATION_SLOT_UPTO_NCHANGES = 10_000
REPLICATION_SLOT_TABLE_NAME = "public.notifications"
# Use the first eight bytes of the slot name as a deterministic signed 64-bit advisory lock ID.
# This is inline with the way we build lock IDs for advisory locks for database migrations.
REPLICATION_ADVISORY_LOCK_ID = struct.unpack(">q", struct.pack("8s", REPLICATION_SLOT_NAME.encode()))[0]


JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
RowData = dict[str, JsonValue]


class ReplicationSlotChangesResult(TypedDict, total=False):
    lock_acquired: Required[bool]
    slot_name: str
    upto_nchanges: int
    changes_count: int
    processed_changes: int
    ignored_changes: int
    service_stats_change_count_buckets: int
    last_lsn: str | None


class ParsedRow(TypedDict):
    table: str
    type: str
    current_row_data: RowData
    previous_row_data: RowData
    nextlsn: str | None
    lsn: str | None


def dao_process_notifications_replication_slot_changes(
    *,
    slot_name: str = REPLICATION_SLOT_NAME,
    upto_nchanges: int = REPLICATION_SLOT_UPTO_NCHANGES,
    advisory_lock_id: int = REPLICATION_ADVISORY_LOCK_ID,
) -> ReplicationSlotChangesResult:
    lock_acquired = False

    try:
        lock_acquired = _try_advisory_lock(advisory_lock_id)

        if not lock_acquired:
            return {
                "lock_acquired": lock_acquired,
                "slot_name": slot_name,
                "upto_nchanges": upto_nchanges,
            }

        # lock acquired, proceed to fetch and process replication slot changes.
        # The batch-level SQL LSN is authoritative when deciding where to advance the replication slot,
        # because we may receive trailing WAL rows for other tables in the same logical slot.
        changes, batch_last_lsn = _get_replication_changes(
            slot_name=slot_name, upto_nchanges=upto_nchanges, table_name=REPLICATION_SLOT_TABLE_NAME
        )

    except Exception:
        current_app.logger.exception("Failed to process replication slot changes")
        raise

    finally:
        if lock_acquired:
            try:
                _advisory_unlock(advisory_lock_id)
            except Exception:
                current_app.logger.exception("Failed to release advisory lock")
                raise


def _try_advisory_lock(lock_id: int) -> bool:
    sql = text("SELECT pg_try_advisory_lock(:lock_id)")
    return bool(db.session.execute(sql, {"lock_id": lock_id}).scalar())


def _advisory_unlock(lock_id: int) -> None:
    db.session.execute(text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": lock_id})


def _get_replication_changes(
    *,
    slot_name: str,
    upto_nchanges: int,
    table_name: str = REPLICATION_SLOT_TABLE_NAME,
) -> tuple[list[ParsedRow], str | None]:
    stmt = text(
        """
        SELECT lsn, data
        FROM pg_logical_slot_peek_changes (
            :slot_name,
            NULL,
            :upto_nchanges,
            'add-tables',
            :table_name,
            'include-lsn',
            :include_lsn,
            'format-version',
            :format_version,
            'include-types',
            :include_types,
            'include-typmod',
            :include_typmod
        )
        """
    )
    rows = list(
        db.session.execute(
            stmt,
            {
                "slot_name": slot_name,
                "upto_nchanges": upto_nchanges,
                "table_name": table_name,
                "include_lsn": "true",
                "format_version": "2",
                "include_types": "false",
                "include_typmod": "false",
            },
        ).mappings()
    )

    parsed_rows: list[ParsedRow] = []
    last_sql_lsn: str | None = None

    for row in rows:
        payload = row.get("data")
        lsn = row.get("lsn")

        if not lsn or not payload or not isinstance(payload, str):
            continue

        last_sql_lsn = lsn
        payload = json.loads(payload)
        parsed_rows.extend(_parse_wal2json_payload(payload, table_name=table_name, default_nextlsn=lsn))

    return parsed_rows, last_sql_lsn


## Helper functions


def _parse_wal2json_payload(
    payload: dict[str, JsonValue], *, table_name: str = REPLICATION_SLOT_TABLE_NAME, default_nextlsn: str | None = None
) -> list[ParsedRow]:
    # wal2json format-version 2 emits one change object per slot row.
    action = payload.get("action")
    change_type = _normalise_change_type(action)
    if change_type in {"begin", "commit", "message", "unknown"}:
        return []

    schema = payload.get("schema")
    table = payload.get("table")
    if not table or not isinstance(table, str):
        return []

    qualified_table_name = f"{schema}.{table}" if schema else table
    if table_name and qualified_table_name != table_name:
        return []

    nextlsn = payload.get("nextlsn") or default_nextlsn
    return [
        {
            "table": table,
            "type": change_type,
            "current_row_data": _extract_row_data(payload),
            "previous_row_data": _extract_previous_row_data(payload),
            "nextlsn": nextlsn if isinstance(nextlsn, str) else None,
            "lsn": default_nextlsn,
        }
    ]


def _normalise_change_type(action: JsonValue) -> str:
    if action is None:
        return "unknown"

    normalised = str(action).upper()
    mapping = {
        "I": "insert",
        "U": "update",
        "D": "delete",
        "B": "begin",
        "C": "commit",
        "M": "message",
    }
    return mapping.get(normalised, str(action).lower())


def _extract_row_data(change: dict[str, JsonValue]) -> RowData:
    return _extract_name_value_rows(change.get("columns", []))


def _extract_previous_row_data(change: dict[str, JsonValue]) -> RowData:
    if change.get("action") in {"U", "D"}:
        return _extract_name_value_rows(change.get("identity", []))

    return {}


def _extract_name_value_rows(rows: JsonValue) -> RowData:
    row_data: RowData = {}
    if not isinstance(rows, list):
        return row_data
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        if name is None:
            continue
        row_data[str(name)] = row.get("value")
    return row_data
