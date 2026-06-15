import json
from collections import Counter
from datetime import date, datetime
from typing import Any
from uuid import UUID

from notifications_utils.timezones import convert_utc_to_bst
from sqlalchemy import text # type: ignore[reportMissingImports]

from app import current_app, db
from app.dao.fact_service_stats_dao import ServiceStatsDimensions, apply_service_stats_change

REPLICATION_SLOT_NAME = "notify_dashboard_replication_slot"
REPLICATION_SLOT_TABLE_NAMES = ("notifications", "notification_history")
REPLICATION_SLOT_UPTO_NCHANGES = 10_000
REPLICATION_ADVISORY_LOCK_ID = 4_009_881
NIL_UUID = UUID("00000000-0000-0000-0000-000000000000")

RowData = dict[str, Any]
ParsedRow = dict[str, Any]
FullDimensions = tuple[date, UUID, UUID, UUID, str, str, str]
ServiceStatsDimensionsKey = tuple[UUID, UUID, str, str]


def dao_process_replication_slot_changes(
    *,
    slot_name: str = REPLICATION_SLOT_NAME,
    upto_nchanges: int = REPLICATION_SLOT_UPTO_NCHANGES,
    advisory_lock_id: int = REPLICATION_ADVISORY_LOCK_ID,
) -> dict[str, int | str | bool | None]:
    lock_acquired = False
    try:
        lock_acquired = _try_advisory_lock(advisory_lock_id)
        if not lock_acquired:
            current_app.logger.info(
                "Replication slot lock not acquired",
                extra={"changes_count": 0, "dao_method": "dao_process_replication_slot_changes"},
            )
            return {
                "lock_acquired": False,
                "changes_count": 0,
                "processed_changes": 0,
                "ignored_changes": 0,
                "service_stats_change_count_buckets": 0,
                "last_nextlsn": None,
            }

        changes = get_replication_changes(
            peek=True,
            slot_name=slot_name,
            upto_nchanges=upto_nchanges,
            table_names=REPLICATION_SLOT_TABLE_NAMES,
            include_lsn=True,
            format_version=1,
            include_types=False,
            include_typmod=False,
        )
        fetched_changes = len(changes)

        if fetched_changes == 0:
            current_app.logger.info(
                "No replication slot changes found",
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
        service_stats_change_counts = _roll_up_service_stats_change_counts(counter)

        for service_stats_key, change_count in service_stats_change_counts.items():
            if change_count == 0:
                continue

            service_id, template_id, notification_type, notification_status = service_stats_key
            dimensions: ServiceStatsDimensions = {
                "service_id": service_id,
                "template_id": template_id,
                "notification_type": notification_type,
                "notification_status": notification_status,
            }
            apply_service_stats_change(dimensions, change_count)

        db.session.commit()

        if last_nextlsn:
            _advance_replication_slot(last_nextlsn, slot_name=slot_name)

        current_app.logger.info(
            "Replication slot changes processed",
            extra={
                "changes_count": fetched_changes,
                "processed_changes": processed_changes,
                "ignored_changes": ignored_changes,
                "service_stats_change_count_buckets": len(service_stats_change_counts),
                "dao_method": "dao_process_replication_slot_changes",
            },
        )

        return {
            "lock_acquired": True,
            "changes_count": fetched_changes,
            "processed_changes": processed_changes,
            "ignored_changes": ignored_changes,
            "service_stats_change_count_buckets": len(service_stats_change_counts),
            "last_nextlsn": last_nextlsn,
        }
    except Exception:
        db.session.rollback()
        raise
    finally:
        if lock_acquired:
            try:
                _advisory_unlock(advisory_lock_id)
            except Exception:
                current_app.logger.exception(
                    "Failed to release advisory lock",
                    extra={"dao_method": "dao_process_replication_slot_changes"},
                )


def get_replication_changes(
    *,
    peek: bool,
    slot_name: str,
    upto_nchanges: int,
    table_names: tuple[str, ...],
    include_lsn: bool,
    format_version: int,
    include_types: bool,
    include_typmod: bool,
) -> list[ParsedRow]:
    function_name = "pg_logical_slot_peek_changes" if peek else "pg_logical_slot_get_changes"
    stmt = text(
        f"""
        SELECT data
        FROM {function_name}(
            :slot_name,
            NULL,
            :upto_nchanges,
            'add-tables',
            :table_names,
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
            "table_names": ",".join(table_names),
            "include_lsn": _to_wal2json_bool(include_lsn),
            "format_version": str(format_version),
            "include_types": _to_wal2json_bool(include_types),
            "include_typmod": _to_wal2json_bool(include_typmod),
        },
    ).mappings()

    parsed_rows: list[ParsedRow] = []
    for row in rows:
        payload = row.get("data")
        if not payload:
            continue

        if isinstance(payload, str):
            payload = json.loads(payload)

        parsed_rows.extend(_parse_wal2json_payload(payload, table_names=table_names))

    return parsed_rows


def _to_wal2json_bool(value: bool) -> str:
    return "true" if value else "false"


def _parse_wal2json_payload(payload: dict[str, Any], *, table_names: tuple[str, ...]) -> list[ParsedRow]:
    parsed_rows: list[ParsedRow] = []

    for change in payload.get("change", []):
        schema = change.get("schema")
        table = change.get("table")
        if not table:
            continue

        qualified_table_name = f"{schema}.{table}" if schema else table
        if table_names and qualified_table_name not in table_names:
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


def get_str_value(row_data: RowData | None, key: str) -> str | None:
    if not row_data:
        return None

    raw_value = row_data.get(key)
    if raw_value is None:
        return None

    return raw_value if isinstance(raw_value, str) else str(raw_value)


def get_notification_status(row_data: RowData | None) -> str | None:
    return get_str_value(row_data, "notification_status") or get_str_value(row_data, "status")


def _try_advisory_lock(lock_id: int) -> bool:
    return bool(db.session.execute(text("SELECT pg_try_advisory_lock(:lock_id)"), {"lock_id": lock_id}).scalar())


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

        if table_name not in {"notifications", "notification_history"}:
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
    notification_type = get_str_value(row_data, "notification_type") or get_str_value(fallback_data, "notification_type")
    job_id = _parse_uuid_value(row_data, "job_id") or _parse_uuid_value(fallback_data, "job_id") or NIL_UUID
    key_type = get_str_value(row_data, "key_type") or get_str_value(fallback_data, "key_type")
    primary_status = get_notification_status(row_data)
    notification_status = primary_status or get_notification_status(fallback_data)
    created_at = _parse_datetime_value(row_data, "created_at") or _parse_datetime_value(fallback_data, "created_at")

    if require_status_from_primary_row and not primary_status:
        return None

    if not service_id or not template_id or not notification_type or not key_type or not notification_status or not created_at:
        return None

    return (
        convert_utc_to_bst(created_at).date(),
        template_id,
        service_id,
        job_id,
        notification_type,
        key_type,
        notification_status,
    )


def _parse_uuid_value(row_data: RowData, key: str) -> UUID | None:
    raw_value = get_str_value(row_data, key)
    if not raw_value:
        return None

    try:
        return UUID(raw_value)
    except ValueError:
        return None


def _parse_datetime_value(row_data: RowData, key: str) -> datetime | None:
    raw_value = get_str_value(row_data, key)
    if not raw_value:
        return None

    normalized = raw_value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _roll_up_service_stats_change_counts(counter: Counter[FullDimensions]) -> Counter[ServiceStatsDimensionsKey]:
    change_counts: Counter[ServiceStatsDimensionsKey] = Counter()
    for dimensions, change_count in counter.items():
        _, template_id, service_id, _, notification_type, _, notification_status = dimensions
        change_counts[(service_id, template_id, notification_type, notification_status)] += change_count

    return change_counts


def _advance_replication_slot(lsn: str, *, slot_name: str) -> None:
    db.session.execute(
        text("SELECT pg_replication_slot_advance(:slot_name, :lsn)"),
        {"slot_name": slot_name, "lsn": lsn},
    )


def _advisory_unlock(lock_id: int) -> None:
    db.session.execute(text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": lock_id})
