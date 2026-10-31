# total=False to make all keys optional by default, except those marked as Required
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
    upsert_notification_status_live_counts,
)

REPLICATION_SLOT_NAME = "notify_wal2json_slot"
REPLICATION_SLOT_UPTO_NCHANGES = 10_000
REPLICATION_SLOT_TABLE_NAME = "public.notifications"
# Use the first eight bytes of the slot name as a deterministic signed 64-bit advisory lock ID.
# This is inline with the way we build lock IDs for advisory locks for database migrations.
REPLICATION_ADVISORY_LOCK_ID = struct.unpack(">q", struct.pack("8s", REPLICATION_SLOT_NAME.encode()))[0]
# Notifications without a job (e.g. sent via the API) are bucketed under a zero UUID, as job_id is part of the
# primary key of ft_notification_status_live (same convention as ft_notification_status).
NO_JOB_ID = UUID("00000000-0000-0000-0000-000000000000")


JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
RowData = dict[str, JsonValue]


class ReplicationSlotChangesResult(TypedDict, total=False):
    lock_acquired: Required[bool]
    slot_name: str
    upto_nchanges: int
    changes_count: int
    processed_changes: int
    ignored_changes: int
    change_count_buckets: int
    last_lsn: str | None


class ParsedRow(TypedDict):
    table: str
    type: str
    current_row_data: RowData
    previous_row_data: RowData
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


def dao_process_notifications_replication_slot_changes(
    *,
    slot_name: str = REPLICATION_SLOT_NAME,
    upto_nchanges: int = REPLICATION_SLOT_UPTO_NCHANGES,
    advisory_lock_id: int = REPLICATION_ADVISORY_LOCK_ID,
) -> ReplicationSlotChangesResult:
    start_time = datetime.now()
    lock_acquired = False

    try:
        lock_acquired = _try_advisory_lock(advisory_lock_id)

        if not lock_acquired:
            return {"lock_acquired": lock_acquired, "slot_name": slot_name}

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
                "slot_name": slot_name,
                "changes_count": fetched_changes,
                "change_count_buckets": 0,
            }

        # This should never happen in normal circumstances as we already have a 0 changes gate above
        # If we have changes but no last SQL LSN, something went wrong and we should raise an error.
        if not batch_last_lsn:
            raise RuntimeError(
                f"No last_lsn found after processing replication slot changes, \
                replication slot {slot_name} will not be advanced. This should not happen under normal circumstances."
            )

        # Build counter up
        counter, processed_changes, ignored_changes = _build_counter_from_changes(changes)

        # Process the fetched replication slot changes to update service statistics.
        _upsert_notification_status_live_count(counter)

        # Advance the replication slot to the last processed SQL LSN
        # to avoid reprocessing the same changes in future runs.
        current_app.logger.info(
            "Advancing replication slot %s to last_lsn=%s",
            slot_name,
            batch_last_lsn,
            extra={"slot_name": slot_name, "last_lsn": batch_last_lsn},
        )
        _advance_replication_slot(batch_last_lsn, slot_name=slot_name)

        # Determine the number of distinct change count buckets based on the counter.
        change_count_buckets = len(counter)

        # Log the result of the replication slot processing for monitoring and debugging purposes.
        current_app.logger.info(
            "%s replication slot changes processed: %s processed, %s ignored, %s change count buckets, last_lsn=%s",
            fetched_changes,
            processed_changes,
            ignored_changes,
            change_count_buckets,
            batch_last_lsn,
            extra={
                "changes_count": fetched_changes,
                "processed_changes": processed_changes,
                "ignored_changes": ignored_changes,
                "change_count_buckets": change_count_buckets,
                "last_lsn": batch_last_lsn,
            },
        )

        # Return a summary of the replication slot processing results
        return {
            "lock_acquired": lock_acquired,
            "changes_count": fetched_changes,
            "processed_changes": processed_changes,
            "ignored_changes": ignored_changes,
            "change_count_buckets": change_count_buckets,
            "last_lsn": batch_last_lsn,
        }
    except Exception:
        # Ensure a failed statement does not poison the session for cleanup queries.
        db.session.rollback()
        current_app.logger.exception("Failed to process replication slot changes")
        raise

    finally:
        if lock_acquired:
            try:
                _advisory_unlock(advisory_lock_id)
            except Exception:
                current_app.logger.exception("Failed to release advisory lock")
                raise

        # Log the total time taken to process the replication slot changes for monitoring and debugging purposes.
        end_time = datetime.now()
        current_app.logger.info(
            "Replication slot changes processed in %s seconds.",
            (end_time - start_time).total_seconds(),
            extra={
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "duration_seconds": (end_time - start_time).total_seconds(),
            },
        )


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
        parsed_rows.extend(_parse_wal2json_payload(payload, table_name=table_name, default_lsn=lsn))

    return parsed_rows, last_sql_lsn


def _upsert_notification_status_live_count(counter) -> None:
    count_changes: list[NotificationStatusLiveDimensions] = []

    for dimensions_key, change_count in counter.items():
        if change_count == 0:
            continue

        bst_date, service_id, template_id, job_id, notification_type, key_type, notification_status = dimensions_key

        count_changes.append(
            {
                "bst_date": bst_date,
                "service_id": service_id,
                "template_id": template_id,
                "job_id": job_id,
                "notification_type": notification_type,
                "key_type": key_type,
                "notification_status": notification_status,
                "notification_count": change_count,
            }
        )

    if count_changes:
        upsert_notification_status_live_counts(count_changes)


def _advance_replication_slot(lsn: str, *, slot_name: str) -> None:
    db.session.execute(
        text("SELECT pg_replication_slot_advance(:slot_name, :lsn)"),
        {"slot_name": slot_name, "lsn": lsn},
    )


## Helper functions


def _parse_wal2json_payload(
    payload: dict[str, JsonValue], *, table_name: str = REPLICATION_SLOT_TABLE_NAME, default_lsn: str | None = None
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

    return [
        {
            "table": table,
            "type": change_type,
            "current_row_data": _extract_row_data(payload),
            "previous_row_data": _extract_previous_row_data(payload),
            "lsn": default_lsn,
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
def _build_counter_from_changes(changes: list[ParsedRow]) -> tuple[Counter[FullDimensions], int, int]:
    counter: Counter[FullDimensions] = Counter()
    processed_changes = 0
    ignored_changes = 0

    for change in changes:
        table_name = change["table"]
        change_type = change["type"]

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

    return counter, processed_changes, ignored_changes


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
    job_id = _parse_uuid_value(row_data, "job_id") or _parse_uuid_value(fallback_data, "job_id") or NO_JOB_ID
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
