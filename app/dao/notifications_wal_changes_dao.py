from typing import Any
from flask import current_app
from sqlalchemy import text # type: ignore[reportMissingImports]
from app import db
import json
from uuid import UUID
from datetime import date, datetime
from collections import Counter
from notifications_utils.timezones import convert_utc_to_bst

REPLICATION_SLOT_NAME = "notify_dashboard_replication_slot"
REPLICATION_SLOT_TABLE_NAME = "public.notifications"
REPLICATION_SLOT_UPTO_NCHANGES = 10_000
REPLICATION_ADVISORY_LOCK_ID = 4_009_881

ParsedRow = dict[str, Any]
RowData = dict[str, Any]
FullDimensions = tuple[date, UUID, UUID, str, str]


def dao_process_notifications_replication_slot_changes(
    *,
    slot_name: str = REPLICATION_SLOT_NAME,
    upto_nchanges: int = REPLICATION_SLOT_UPTO_NCHANGES,
    advisory_lock_id: int = REPLICATION_ADVISORY_LOCK_ID,
) -> dict[str, int | str | bool | None]:
    lock_acquired = False
    current_app.logger.info("-----------------------------------------------------------")
    current_app.logger.info("[STARTED] Replication slot changes")
    current_app.logger.info("-----------------------------------------------------------")

    try:
        lock_acquired = _try_advisory_lock(advisory_lock_id)

        if not lock_acquired:
            current_app.logger.info("[SKIPPED] Replication slot changes")
            return {
                "lock_acquired": lock_acquired,
                "slot_name": slot_name,
                "upto_nchanges": upto_nchanges,
            }

        current_app.logger.info(f"[LOCK ACQUIRED] Replication slot changes (lock = {lock_acquired})")

        changes = _get_replication_changes(
            slot_name=slot_name,
            upto_nchanges=upto_nchanges,
            table_name=REPLICATION_SLOT_TABLE_NAME
        )
        fetched_changes = len(changes)

        if fetched_changes == 0:
            current_app.logger.info(
                "[NO CHANGES] No replication slot changes found",
                extra={"changes_count": 0, "dao_method": "dao_process_replication_slot_changes"},
            )
            return {
                "lock_acquired": True,
                "changes_count": 0,
                "processed_changes": 0,
                "ignored_changes": 0,
                "service_stats_change_count_buckets": 0,
                "last_nextlsn": None,
            }

        counter, processed_changes, ignored_changes, last_nextlsn = _build_counter_from_changes(changes)

        current_app.logger.info(
            {
                "counter": counter,
                "processed_changes": processed_changes,
                "ignored_changes": ignored_changes,
                "last_nextlsn": last_nextlsn,
            }
        )


        current_app.logger.info(f"[FETCHED] {fetched_changes} replication slot changes")
    except Exception:
        # Ensure a failed statement does not poison the session for cleanup queries.
        db.session.rollback()
        current_app.logger.exception("[FAILED] Replication slot changes")
        raise
    finally:
        if lock_acquired:
            current_app.logger.info(
                f"[RELEASING LOCK] Replication slot changes (lock = {lock_acquired})",
            )
            _advisory_unlock(advisory_lock_id)

    current_app.logger.info("-----------------------------------------------------------")
    current_app.logger.info(f"[FINISHED] Replication slot changes")
    current_app.logger.info("-----------------------------------------------------------")

    return {
        "lock_acquired": lock_acquired,
        "slot_name": slot_name,
        "upto_nchanges": upto_nchanges,
    }

def _try_advisory_lock(lock_id: int) -> bool:
    # The celery beat scheduler runs multiple instances of the same task in parallel,
    # so we need to use an advisory lock to ensure that only one instance of the task is running at a time.
    # Additional check is added to see if the lock is already held by the current process,
    # in which case we don't want to try to acquire it again as there would already be one in progress.
    sql = text("""
        WITH already_held AS (
            SELECT EXISTS (
                SELECT 1
                FROM pg_locks
                WHERE locktype = 'advisory'
                  AND pid = pg_backend_pid()
                  AND granted
                  AND classid = CAST((CAST(:lock_id AS bigint) >> 32) AS integer)
                  AND objid   = CAST((CAST(:lock_id AS bigint) & 4294967295) AS integer)
                  AND objsubid = 1
            ) AS held
        )
        SELECT CASE
                 WHEN held THEN FALSE
                 ELSE pg_try_advisory_lock(:lock_id)
               END
        FROM already_held
    """)
    return bool(db.session.execute(sql, {"lock_id": lock_id}).scalar())

def _advisory_unlock(lock_id: int) -> None:
    db.session.execute(text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": lock_id})

def _get_replication_changes(
    *,
    slot_name: str,
    upto_nchanges: int,
    table_name: str = REPLICATION_SLOT_TABLE_NAME,
) -> list[ParsedRow]:
    stmt = text(
        f"""
        SELECT data
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
    rows = db.session.execute(
        stmt,
        {
            "slot_name": slot_name,
            "upto_nchanges": upto_nchanges,
            "table_name": table_name,
            "include_lsn": 'true',
            "format_version": '1',
            "include_types": 'false',
            "include_typmod": 'false',
        },
    ).mappings()

    parsed_rows: list[ParsedRow] = []
    for row in rows:
        payload = row.get("data")
        if not payload:
            continue

        if isinstance(payload, str):
            payload = json.loads(payload)

        parsed_rows.extend(_parse_wal2json_payload(payload, table_name=table_name))

    return parsed_rows

def _parse_wal2json_payload(payload: dict[str, Any], *, table_name: str = REPLICATION_SLOT_TABLE_NAME) -> list[ParsedRow]:
    parsed_rows: list[ParsedRow] = []

    for change in payload.get("change", []):
        schema = change.get("schema")
        table = change.get("table")
        if not table:
            continue

        qualified_table_name = f"{schema}.{table}" if schema else table
        if table_name and qualified_table_name != table_name:
            continue

        parsed_rows.append(
            {
                "table": table,
                "type": change.get("kind") or change.get("type"),
                "current_row_data": _extract_row_data(change),
                "previous_row_data": _extract_previous_row_data(change),
                "nextlsn": change.get("nextlsn") or payload.get("nextlsn"),
            }
        )

    return parsed_rows

def _extract_row_data(change: dict[str, Any]) -> RowData:
    if "columnnames" in change and "columnvalues" in change:
        return _zip_values(change["columnnames"], change["columnvalues"])

    if "columns" in change:
        row_data: RowData = {}
        for column in change["columns"]:
            name = column.get("name")
            if name:
                row_data[name] = column.get("value")
        return row_data

    return {}


def _extract_previous_row_data(change: dict[str, Any]) -> RowData:
    oldkeys = change.get("oldkeys") or {}
    if "keynames" in oldkeys and "keyvalues" in oldkeys:
        return _zip_values(oldkeys["keynames"], oldkeys["keyvalues"])

    if "keys" in oldkeys:
        row_data: RowData = {}
        for column in oldkeys["keys"]:
            name = column.get("name")
            if name:
                row_data[name] = column.get("value")
        return row_data

    return {}

def _zip_values(names: list[Any], values: list[Any]) -> RowData:
    return {str(name): value for name, value in zip(names, values)}

def _build_counter_from_changes(changes: list[ParsedRow]) -> tuple[Counter[FullDimensions], int, int, str | None]:
    counter: Counter[FullDimensions] = Counter()
    processed_changes = 0
    ignored_changes = 0
    last_nextlsn: str | None = None

    current_app.logger.info(f"[PROCESSING] {len(changes)} replication slot changes")
    current_app.logger.info(f"[PROCESSING] {changes}")

    for change in changes:
        table_name = change["table"]
        change_type = change["type"]
        if change.get("nextlsn"):
            last_nextlsn = change["nextlsn"]

        if table_name != REPLICATION_SLOT_TABLE_NAME.split(".")[-1]:
            ignored_changes += 1
            continue

        if change_type == "insert":
            dimensions = _build_dimensions(change, use_previous_row=False)
            if not dimensions:
                ignored_changes += 1
                continue

            counter[dimensions] += 1
            processed_changes += 1
            continue

        if change_type == "update":
            updated = False
            new_dimensions = _build_dimensions(change, use_previous_row=False)
            if new_dimensions:
                counter[new_dimensions] += 1
                updated = True

            old_dimensions = _build_dimensions(change, use_previous_row=True, require_status_from_primary_row=True)
            if old_dimensions:
                counter[old_dimensions] -= 1
                updated = True

            if not updated:
                ignored_changes += 1
                continue

            processed_changes += 1
            continue

        ignored_changes += 1

    return counter, processed_changes, ignored_changes, last_nextlsn

def _build_dimensions(
    change: ParsedRow,
    *,
    use_previous_row: bool,
    require_status_from_primary_row: bool = False,
) -> FullDimensions | None:
    if use_previous_row:
        row_data = change["previous_row_data"]
        fallback_data = change["current_row_data"]
    else:
        row_data = change["current_row_data"]
        fallback_data = change["previous_row_data"]

    service_id = _parse_uuid_value(row_data, "service_id") or _parse_uuid_value(fallback_data, "service_id")
    template_id = _parse_uuid_value(row_data, "template_id") or _parse_uuid_value(fallback_data, "template_id")
    notification_type = _get_str_value(row_data, "notification_type") or _get_str_value(fallback_data, "notification_type")
    key_type = _get_str_value(row_data, "key_type") or _get_str_value(fallback_data, "key_type")
    primary_status = row_data.get("notification_status")
    notification_status = primary_status or fallback_data.get("notification_status")
    created_at = _parse_datetime_value(row_data, "created_at") or _parse_datetime_value(fallback_data, "created_at")

    if key_type == "test":
        return None

    if require_status_from_primary_row and not notification_status:
        return None

    if not service_id or not template_id or not notification_type or not key_type or not notification_status or not created_at:
        return None

    return (
        convert_utc_to_bst(created_at).date(),
        template_id,
        service_id,
        notification_type,
        notification_status,
    )

def _parse_uuid_value(row_data: RowData, key: str) -> UUID | None:
    raw_value = _get_str_value(row_data, key)
    if not raw_value:
        return None

    try:
        return UUID(raw_value)
    except ValueError:
        return None

def _get_str_value(row_data: RowData | None, key: str) -> str | None:
    if not row_data:
        return None

    raw_value = row_data.get(key)
    if raw_value is None:
        return None

    return raw_value if isinstance(raw_value, str) else str(raw_value)

def _parse_datetime_value(row_data: RowData, key: str) -> datetime | None:
    raw_value = _get_str_value(row_data, key)
    if not raw_value:
        return None

    normalized = raw_value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None