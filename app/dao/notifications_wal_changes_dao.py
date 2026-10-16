import json
import struct
from collections import Counter
from datetime import date, datetime
from typing import NamedTuple, Required, TypedDict
from uuid import UUID

from flask import current_app
from notifications_utils.timezones import convert_utc_to_bst
from sqlalchemy import text  # type: ignore[reportMissingImports]

from app import db
from app.dao.fact_notification_status_live_dao import (
    NotificationStatusLiveDimensions,
    apply_notification_status_live_change,
)

REPLICATION_SLOT_NAME = "notify_wal2json_slot"
REPLICATION_SLOT_TABLE_NAME = "public.notifications"
REPLICATION_SLOT_UPTO_NCHANGES = 10_000
LOG_KEY = "[notifications_wal_changes_dao]"  # Prefix for all log messages in this module

# Use the first eight bytes of the slot name as a deterministic signed 64-bit advisory lock ID.
# This is inline with the way we build lock IDs for advisory locks for database migrations.
REPLICATION_ADVISORY_LOCK_ID = struct.unpack(">q", struct.pack("8s", REPLICATION_SLOT_NAME.encode()))[0]

JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
RowData = dict[str, JsonValue]


class ParsedRow(TypedDict):
    table: str
    type: str
    current_row_data: RowData
    previous_row_data: RowData
    nextlsn: str | None
    lsn: str | None


# This must remain a hashable tuple for use as a Counter key.
# NotificationStatusLiveDimensions is a TypedDict, so use a tuple as the Counter key.
class FullDimensions(NamedTuple):
    bst_date: date
    service_id: UUID
    template_id: UUID
    job_id: UUID
    notification_type: str
    key_type: str
    notification_status: str


# total=False to make all keys optional by default, except those marked as Required
class ReplicationSlotChangesResult(TypedDict, total=False):
    lock_acquired: Required[bool]
    slot_name: str
    upto_nchanges: int
    changes_count: int
    processed_changes: int
    ignored_changes: int
    service_stats_change_count_buckets: int
    last_lsn: str | None


def dao_process_notifications_replication_slot_changes(
    *,
    slot_name: str = REPLICATION_SLOT_NAME,
    upto_nchanges: int = REPLICATION_SLOT_UPTO_NCHANGES,
    advisory_lock_id: int = REPLICATION_ADVISORY_LOCK_ID,
) -> ReplicationSlotChangesResult:
    lock_acquired = False
    start_time = datetime.now()

    try:
        lock_acquired = _try_advisory_lock(advisory_lock_id)

        if not lock_acquired:
            # Skip replication slot changes when lock not acquired
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
        fetched_changes = len(changes)

        if not changes or fetched_changes == 0:
            return {
                "lock_acquired": lock_acquired,
                "changes_count": 0,
                "processed_changes": 0,
                "ignored_changes": 0,
                "service_stats_change_count_buckets": 0,
                "last_lsn": batch_last_lsn,
            }

        # This should never happen in normal circumstances as we already have a 0 changes gate above
        # If we have changes but no last SQL LSN, something went wrong and we should raise an error.
        if not batch_last_lsn:
            raise RuntimeError(
                f"{LOG_KEY} No last_lsn found after processing replication slot changes, \
                replication slot {slot_name} will not be advanced. This should not happen under normal circumstances."
            )

        # Process the fetched replication slot changes to update service statistics.
        processed_changes, ignored_changes, service_stats_change_counts = _process_changes(changes)

        # Advance the replication slot to the last processed SQL LSN
        # to avoid reprocessing the same changes in future runs.
        current_app.logger.info(
            "%s Advancing replication slot %s to last_lsn=%s",
            LOG_KEY,
            slot_name,
            batch_last_lsn,
        )
        _advance_replication_slot(batch_last_lsn, slot_name=slot_name)

        # Log the result of the replication slot processing for monitoring and debugging purposes.
        current_app.logger.info(
            "%s %s replication slot changes processed: %s processed, %s ignored, "
            "%s service stats change count buckets, last_lsn=%s",
            LOG_KEY,
            fetched_changes,
            processed_changes,
            ignored_changes,
            len(service_stats_change_counts),
            batch_last_lsn,
        )

        # Return a summary of the replication slot processing results
        return {
            "lock_acquired": lock_acquired,
            "changes_count": fetched_changes,
            "processed_changes": processed_changes,
            "ignored_changes": ignored_changes,
            "service_stats_change_count_buckets": len(service_stats_change_counts),
            "last_lsn": batch_last_lsn,
        }
    except Exception:
        # Ensure a failed statement does not poison the session for cleanup queries.
        db.session.rollback()
        current_app.logger.exception("%s FAILED: Replication slot changes", LOG_KEY)
        raise
    finally:
        # Release the advisory lock if it was acquired, and log any exceptions that occur during the release process.
        if lock_acquired:
            try:
                _advisory_unlock(advisory_lock_id)
            except Exception:
                current_app.logger.exception(
                    "%s Failed to release advisory lock",
                    LOG_KEY,
                    extra={"dao_method": "dao_process_notifications_replication_slot_changes"},
                )
                raise

        # Log the total time taken to process the replication slot changes for monitoring and debugging purposes.
        end_time = datetime.now()
        current_app.logger.info(
            "%s Replication slot changes processed in %s seconds.",
            LOG_KEY,
            (end_time - start_time).total_seconds(),
            extra={
                "dao_method": "dao_process_notifications_replication_slot_changes",
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "duration_seconds": (end_time - start_time).total_seconds(),
            },
        )


def _try_advisory_lock(lock_id: int) -> bool:
    # The celery beat scheduler runs multiple instances of the same task in parallel,
    # so we need to use an advisory lock to ensure that only one instance of the task is running at a time.
    # Additional check is added to see if the lock is already held by the current process,
    # in which case we don't want to try to acquire it again as there would already be one in progress.
    # In pg_locks, pid identifies this backend and granted excludes queued locks. A bigint advisory key
    # is split across classid (upper 32 bits) and objid (lower 32 bits). The 4294967295 mask is
    # 2^32 - 1 (32 one-bits), so it selects objid's lower bits; objsubid = 1 identifies the bigint
    # key form, while objsubid = 2 identifies the two-integer key form.
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
        if lsn:
            last_sql_lsn = lsn
        if not payload:
            continue

        if isinstance(payload, str):
            payload = json.loads(payload)

        parsed_rows.extend(_parse_wal2json_payload(payload, table_name=table_name, default_nextlsn=lsn))

    # advance the replication slot to the last SQL row LSN even when the terminal WAL rows are
    # for a different table in the same logical slot; otherwise the slot can stop advancing on the
    # last relevant notification change instead of the actual last row returned by PostgreSQL.
    if not parsed_rows and rows and last_sql_lsn:
        current_app.logger.info(
            "%s Advancing replication slot %s to last_lsn=%s (batch boundary)",
            LOG_KEY,
            slot_name,
            last_sql_lsn,
        )
        _advance_replication_slot(last_sql_lsn, slot_name=slot_name)

    return parsed_rows, last_sql_lsn


def _process_changes(changes):
    # Process the fetched replication slot changes to update live notification status counts.
    # The slot advance boundary must use the SQL-reported LSN, not the row-level wal2json nextlsn.
    counter, processed_changes, ignored_changes, _ = _build_counter_from_changes(changes)

    # Apply the change counts to the database
    for dimensions_key, change_count in counter.items():
        if change_count == 0:
            continue

        bst_date, service_id, template_id, job_id, notification_type, key_type, notification_status = dimensions_key
        dimensions: NotificationStatusLiveDimensions = {
            "bst_date": bst_date,
            "service_id": service_id,
            "template_id": template_id,
            "job_id": job_id,
            "notification_type": notification_type,
            "key_type": key_type,
            "notification_status": notification_status,
        }
        apply_notification_status_live_change(dimensions, change_count)

    return processed_changes, ignored_changes, counter


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


# Ignoring C901 (function is too complex) because this function is inherently complex due to the
# nature of processing replication slot changes and building counters from them.
# ruff: noqa: C901
def _build_counter_from_changes(changes: list[ParsedRow]) -> tuple[Counter[FullDimensions], int, int, str | None]:
    counter: Counter[FullDimensions] = Counter()
    processed_changes = 0
    ignored_changes = 0
    last_lsn: str | None = None

    for change in changes:
        table_name = change["table"]
        change_type = change["type"]
        if change.get("lsn"):
            last_lsn = change["lsn"]
        elif change.get("nextlsn"):
            last_lsn = change["nextlsn"]

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

    return counter, processed_changes, ignored_changes, last_lsn


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
    job_id = _parse_uuid_value(row_data, "job_id") or _parse_uuid_value(fallback_data, "job_id")
    notification_type = _get_str_value(row_data, "notification_type") or _get_str_value(
        fallback_data, "notification_type"
    )
    key_type = _get_str_value(row_data, "key_type") or _get_str_value(fallback_data, "key_type")
    primary_status = _get_str_value(row_data, "notification_status")
    notification_status = primary_status or _get_str_value(fallback_data, "notification_status")
    created_at = _parse_datetime_value(row_data, "created_at") or _parse_datetime_value(fallback_data, "created_at")

    # WAL update payloads may omit unchanged columns, but the old dimensions must use the previous
    # row's status. Falling back to the current status here would subtract the new bucket instead
    # of the old bucket and leave the service statistics counts incorrect.
    if require_status_from_primary_row and not primary_status:
        return None

    if (
        not service_id
        or not template_id
        or not job_id
        or not notification_type
        or not key_type
        or not notification_status
        or not created_at
    ):
        return None

    return FullDimensions(
        bst_date=convert_utc_to_bst(created_at).date(),
        service_id=service_id,
        template_id=template_id,
        job_id=job_id,
        notification_type=notification_type,
        key_type=key_type,
        notification_status=notification_status,
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


def _advance_replication_slot(lsn: str, *, slot_name: str) -> None:
    db.session.execute(
        text("SELECT pg_replication_slot_advance(:slot_name, :lsn)"),
        {"slot_name": slot_name, "lsn": lsn},
    )
