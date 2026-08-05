from typing import Any
from flask import current_app
from sqlalchemy import text # type: ignore[reportMissingImports]
from app import db
import json

REPLICATION_SLOT_NAME = "notify_dashboard_replication_slot"
REPLICATION_SLOT_TABLE_NAME = "public.notifications"
REPLICATION_SLOT_UPTO_NCHANGES = 10_000
REPLICATION_ADVISORY_LOCK_ID = 4_009_881

ParsedRow = dict[str, Any]
RowData = dict[str, Any]

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

