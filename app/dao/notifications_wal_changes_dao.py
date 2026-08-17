import json
from collections import Counter
from datetime import date, datetime
from typing import Any
from uuid import UUID

from flask import current_app
from notifications_utils.timezones import convert_utc_to_bst
from sqlalchemy import text  # type: ignore[reportMissingImports]

from app import db
from app.dao.fact_service_stats_dao import ServiceStatsDimensions, apply_service_stats_change

REPLICATION_SLOT_NAME = "notify_dashboard_replication_slot"
REPLICATION_SLOT_TABLE_NAME = "public.notifications"
REPLICATION_SLOT_UPTO_NCHANGES = 10_000
REPLICATION_ADVISORY_LOCK_ID = 4_009_881

ParsedRow = dict[str, Any]
RowData = dict[str, Any]
FullDimensions = tuple[date, UUID, UUID, str, str]
ServiceStatsDimensionsKey = tuple[date, UUID, UUID, str, str]


def dao_process_notifications_replication_slot_changes(
    *,
    slot_name: str = REPLICATION_SLOT_NAME,
    upto_nchanges: int = REPLICATION_SLOT_UPTO_NCHANGES,
    advisory_lock_id: int = REPLICATION_ADVISORY_LOCK_ID,
) -> dict[str, int | str | bool | None]:
    lock_acquired = False

    try:
        lock_acquired = _try_advisory_lock(advisory_lock_id)

        if not lock_acquired:
            # Skip replication slot changes when lock not acquired
            return {
                "lock_acquired": lock_acquired,
                "slot_name": slot_name,
                "upto_nchanges": upto_nchanges,
            }

        # lock acquired, proceed to fetch and process replication slot changes
        changes = _get_replication_changes(
            slot_name=slot_name, upto_nchanges=upto_nchanges, table_name=REPLICATION_SLOT_TABLE_NAME
        )
        fetched_changes = len(changes)

        if fetched_changes == 0:
            # No changes to process, return early with lock acquired
            return {
                "lock_acquired": True,
                "changes_count": 0,
                "processed_changes": 0,
                "ignored_changes": 0,
                "service_stats_change_count_buckets": 0,
                "last_nextlsn": None,
            }

        # Process the fetched replication slot changes to update service statistics
        counter, processed_changes, ignored_changes, last_nextlsn = _build_counter_from_changes(changes)

        # Aggregate the counter into service statistics change counts for each unique dimensions tuple
        service_stats_change_counts = _aggregate_service_stats_change_counts(counter)

        # Apply the aggregated service statistics change counts to the database
        for service_stats_key, change_count in service_stats_change_counts.items():
            if change_count == 0:
                continue

            bst_date, service_id, template_id, notification_type, notification_status = service_stats_key
            dimensions: ServiceStatsDimensions = {
                "bst_date": bst_date,
                "service_id": service_id,
                "template_id": template_id,
                "notification_type": notification_type,
                "notification_status": notification_status,
            }
            apply_service_stats_change(dimensions, change_count)

        # Commit the changes to the database after processing all replication slot changes
        db.session.commit()

        # Advance the replication slot to the last processed LSN to avoid reprocessing the same changes in future runs
        if last_nextlsn:
            _advance_replication_slot(last_nextlsn, slot_name=slot_name)

        # Return a summary of the replication slot processing results
        return {
            "lock_acquired": True,
            "changes_count": fetched_changes,
            "processed_changes": processed_changes,
            "ignored_changes": ignored_changes,
            "service_stats_change_count_buckets": len(service_stats_change_counts),
            "last_nextlsn": last_nextlsn,
        }
    except Exception:
        # Ensure a failed statement does not poison the session for cleanup queries.
        db.session.rollback()
        current_app.logger.exception("[FAILED] Replication slot changes")
        raise
    finally:
        # Release the advisory lock if it was acquired, and log any exceptions that occur during the release process.
        if lock_acquired:
            try:
                _advisory_unlock(advisory_lock_id)
            except Exception:
                current_app.logger.exception(
                    "Failed to release advisory lock",
                    extra={"dao_method": "dao_process_replication_slot_changes"},
                )


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
        """
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
            "include_lsn": "true",
            "format_version": "2",
            "include_types": "false",
            "include_typmod": "false",
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


def _parse_wal2json_payload(
    payload: dict[str, Any], *, table_name: str = REPLICATION_SLOT_TABLE_NAME
) -> list[ParsedRow]:
    parsed_rows: list[ParsedRow] = []

    # The allows support for format version 1 as well as version 2 of wal2json.
    # In version 1, the payload is a single change object, while in version 2, the payload is a list of change objects.
    raw_changes = payload.get("change")
    if raw_changes is None:
        if payload.get("table") and payload.get("schema") and payload.get("action") in {"I", "U", "D"}:
            raw_changes = [payload]
        else:
            return parsed_rows
    elif not isinstance(raw_changes, list):
        raw_changes = [raw_changes]

    # Parse each change object in the raw_changes list and extract relevant information.
    for change in raw_changes:
        if not isinstance(change, dict):
            continue

        action = change.get("action") or change.get("kind") or change.get("type")
        change_type = _normalise_change_type(action)
        if change_type in {"begin", "commit", "message"}:
            continue

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
                "type": change_type,
                "current_row_data": _extract_row_data(change),
                "previous_row_data": _extract_previous_row_data(change),
                "nextlsn": change.get("nextlsn") or payload.get("nextlsn"),
            }
        )

    current_app.logger.info(
        "Parsed replication slot changes")

    current_app.logger.info(
        f"Parsed {len(parsed_rows)} changes from replication slot '{table_name}' with payload: {payload}")

    return parsed_rows


def _normalise_change_type(action: Any) -> str:
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


def _extract_row_data(change: dict[str, Any]) -> RowData:
    if "columnnames" in change and "columnvalues" in change:
        return _zip_values(change["columnnames"], change["columnvalues"])

    if "columns" in change:
        return _extract_name_value_rows(change["columns"])

    if "identity" in change and change.get("action") in {"D", "U", "I"}:
        return _extract_name_value_rows(change["identity"])

    return {}


def _extract_previous_row_data(change: dict[str, Any]) -> RowData:
    oldkeys = change.get("oldkeys") or {}
    if "keynames" in oldkeys and "keyvalues" in oldkeys:
        return _zip_values(oldkeys["keynames"], oldkeys["keyvalues"])

    if "keys" in oldkeys:
        return _extract_name_value_rows(oldkeys["keys"])

    if "identity" in change and change.get("action") in {"U", "D"}:
        return _extract_name_value_rows(change["identity"])

    return {}


def _extract_name_value_rows(rows: list[Any]) -> RowData:
    row_data: RowData = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        if name is None:
            continue
        row_data[str(name)] = row.get("value")
    return row_data


def _zip_values(names: list[Any], values: list[Any]) -> RowData:
    return {str(name): value for name, value in zip(names, values, strict=True) if name is not None}


def _build_counter_from_changes(changes: list[ParsedRow]) -> tuple[Counter[FullDimensions], int, int, str | None]:
    counter: Counter[FullDimensions] = Counter()
    processed_changes = 0
    ignored_changes = 0
    last_nextlsn: str | None = None

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
    notification_type = _get_str_value(row_data, "notification_type") or _get_str_value(
        fallback_data, "notification_type"
    )
    key_type = _get_str_value(row_data, "key_type") or _get_str_value(fallback_data, "key_type")
    primary_status = row_data.get("notification_status")
    notification_status = primary_status or fallback_data.get("notification_status")
    created_at = _parse_datetime_value(row_data, "created_at") or _parse_datetime_value(fallback_data, "created_at")

    # If the key_type is "test", we ignore this change and return None to indicate
    # that it should not be processed further.
    if key_type == "test":
        return None

    if require_status_from_primary_row and not notification_status:
        return None

    if (
        not service_id
        or not template_id
        or not notification_type
        or not key_type
        or not notification_status
        or not created_at
    ):
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


def _aggregate_service_stats_change_counts(counter: Counter[FullDimensions]) -> Counter[ServiceStatsDimensionsKey]:
    change_counts: Counter[ServiceStatsDimensionsKey] = Counter()
    for dimensions, change_count in counter.items():
        bst_date, template_id, service_id, notification_type, notification_status = dimensions
        change_counts[(bst_date, service_id, template_id, notification_type, notification_status)] += change_count

    return change_counts


def _advance_replication_slot(lsn: str, *, slot_name: str) -> None:
    db.session.execute(
        text("SELECT pg_replication_slot_advance(:slot_name, :lsn)"),
        {"slot_name": slot_name, "lsn": lsn},
    )
