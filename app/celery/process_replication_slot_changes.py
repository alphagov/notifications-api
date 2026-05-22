from collections import Counter
from datetime import date, datetime
from uuid import UUID

from notifications_utils.timezones import convert_utc_to_bst
from sqlalchemy import text

from app import current_app, db, notify_celery
from app.cronitor import cronitor
from app.dao.service_stats_dao import ServiceStatsDimensions, apply_service_stats_delta
from app.replication.replication_changes_utils import (
    ParsedRow,
    RowData,
    get_notification_status,
    get_replication_changes,
    get_str_value,
)

REPLICATION_SLOT_NAME = "notify_dashboard_replication_slot"
REPLICATION_SLOT_UPTO_NCHANGES = 10_000
REPLICATION_ADVISORY_LOCK_ID = 4_009_881
NIL_UUID = UUID("00000000-0000-0000-0000-000000000000")

type FullDimensions = tuple[date, UUID, UUID, UUID, str, str, str]
type ServiceStatsDimensionsKey = tuple[UUID, UUID, str, str]


# 1. Task entrypoint for consuming replication slot changes and applying aggregate deltas
# into the service stats table. This task is lock-guarded so only one worker processes
# and advances the slot at a time.
@notify_celery.task(bind=True, name="check-replication-slot-changes")
@cronitor("check-replication-slot-changes")
def check_replication_slot_changes(self):
    lock_acquired = False
    try:
        with current_app.app_context():
            lock_acquired = _try_advisory_lock(REPLICATION_ADVISORY_LOCK_ID)
            if not lock_acquired:
                current_app.logger.info(
                    "Replication slot lock not acquired",
                    extra={"celery_task": "check-replication-slot-changes"},
                )
                return

            changes = get_replication_changes(
                peek=True,
                slot_name=REPLICATION_SLOT_NAME,
                upto_nchanges=REPLICATION_SLOT_UPTO_NCHANGES,
                table_names=("public.notifications", "public.notification_history"),
                include_lsn=True,
                format_version=1,
                include_types=False,
                include_typmod=False,
            )
            fetched_changes = len(changes)

            if fetched_changes == 0:
                current_app.logger.info(
                    "No replication slot changes found",
                    extra={"celery_task": "check-replication-slot-changes", "changes_count": 0},
                )
                return

            counter, processed_changes, ignored_changes, last_nextlsn = _build_counter_from_changes(changes)
            service_stats_deltas = _roll_up_service_stats_deltas(counter)

            for service_stats_key, delta in service_stats_deltas.items():
                if delta == 0:
                    continue

                service_id, template_id, notification_type, notification_status = service_stats_key
                dimensions: ServiceStatsDimensions = {
                    "service_id": service_id,
                    "template_id": template_id,
                    "notification_type": notification_type,
                    "notification_status": notification_status,
                }
                apply_service_stats_delta(dimensions, delta)

            db.session.commit()
            if last_nextlsn:
                _advance_replication_slot(last_nextlsn)

            current_app.logger.info(
                "Replication slot changes processed",
                extra={
                    "celery_task": "check-replication-slot-changes",
                    "changes_count": fetched_changes,
                    "processed_changes": processed_changes,
                    "ignored_changes": ignored_changes,
                    "service_stats_delta_buckets": len(service_stats_deltas),
                },
            )
    except Exception as exc:
        db.session.rollback()
        retry_count = self.request.retries
        if retry_count < 3:
            raise self.retry(exc=exc, countdown=2**retry_count) from exc

        current_app.logger.error(
            "Replication slot query failed after 3 retries",
            exc_info=True,
            extra={"celery_task": "check-replication-slot-changes"},
        )
        raise
    finally:
        if lock_acquired:
            try:
                _advisory_unlock(REPLICATION_ADVISORY_LOCK_ID)
            except Exception:
                current_app.logger.exception(
                    "Failed to release advisory lock",
                    extra={"celery_task": "check-replication-slot-changes"},
                )


# 2. Attempt to acquire a Postgres advisory lock used to serialize replication processing.
# Returns True when this worker owns the lock and can proceed safely.
def _try_advisory_lock(lock_id: int) -> bool:
    return bool(db.session.execute(text("SELECT pg_try_advisory_lock(:lock_id)"), {"lock_id": lock_id}).scalar())


# 3. Parse a list of WAL-derived row changes into fine-grained stats deltas keyed by full
# dimensions. Also tracks processing counters and the latest LSN that was seen.
def _build_counter_from_changes(changes: list[ParsedRow]) -> tuple[Counter[FullDimensions], int, int, str | None]:
    counter: Counter[FullDimensions] = Counter()
    processed_changes = 0
    ignored_changes = 0
    last_nextlsn: str | None = None

    for change in changes:
        table_name = change["table"]
        change_type = change["type"]
        if change["nextlsn"]:
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

            old_dimensions = _build_dimensions(change, use_previous_row=True)
            if old_dimensions:
                counter[old_dimensions] -= 1
                updated = True

            if not updated:
                ignored_changes += 1
                continue

            processed_changes += 1
            continue

        if change_type == "delete":
            if table_name == "notification_history":
                ignored_changes += 1
                continue

            dimensions = _build_dimensions(change, use_previous_row=True)
            if not dimensions:
                ignored_changes += 1
                continue

            counter[dimensions] -= 1
            processed_changes += 1
            continue

        ignored_changes += 1

    return counter, processed_changes, ignored_changes, last_nextlsn


# 4. Build the complete per-notification dimensions tuple from either the current row or
# previous row image, with fallback across both when one side lacks a value.
def _build_dimensions(change: ParsedRow, *, use_previous_row: bool) -> FullDimensions | None:
    if use_previous_row:
        row_data = change["previous_row_data"]
        fallback_data = change["current_row_data"]
    else:
        row_data = change["current_row_data"]
        fallback_data = change["previous_row_data"]

    service_id = _parse_uuid_value(row_data, "service_id") or _parse_uuid_value(fallback_data, "service_id")
    template_id = _parse_uuid_value(row_data, "template_id") or _parse_uuid_value(fallback_data, "template_id")
    notification_type = get_str_value(row_data, "notification_type") or get_str_value(
        fallback_data, "notification_type"
    )
    job_id = _parse_uuid_value(row_data, "job_id") or _parse_uuid_value(fallback_data, "job_id") or NIL_UUID
    key_type = get_str_value(row_data, "key_type") or get_str_value(fallback_data, "key_type")
    notification_status = get_notification_status(row_data) or get_notification_status(fallback_data)
    created_at = _parse_datetime_value(row_data, "created_at") or _parse_datetime_value(fallback_data, "created_at")

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


# 5. Safely parse a UUID field from row data. Invalid or missing values are treated as None
# so malformed entries do not break replication processing.
def _parse_uuid_value(row_data: RowData, key: str) -> UUID | None:
    raw_value = get_str_value(row_data, key)
    if not raw_value:
        return None

    try:
        return UUID(raw_value)
    except ValueError:
        return None


# 6. Parse ISO-like datetime values from replication payloads, normalizing trailing "Z"
# to a UTC offset format accepted by datetime.fromisoformat.
def _parse_datetime_value(row_data: RowData, key: str) -> datetime | None:
    raw_value = get_str_value(row_data, key)
    if not raw_value:
        return None

    normalized = raw_value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


# 7. Collapse full-dimension deltas down to service stats dimensions used by
# app.dao.service_stats_dao.apply_service_stats_delta.
def _roll_up_service_stats_deltas(counter: Counter[FullDimensions]) -> Counter[ServiceStatsDimensionsKey]:
    deltas: Counter[ServiceStatsDimensionsKey] = Counter()
    for dimensions, delta in counter.items():
        _, template_id, service_id, _, notification_type, _, notification_status = dimensions
        deltas[(service_id, template_id, notification_type, notification_status)] += delta

    return deltas


# 8. Advance the logical replication slot after successful commit so processed changes are
# acknowledged and are not replayed on the next task run.
def _advance_replication_slot(lsn: str) -> None:
    db.session.execute(
        text("SELECT pg_replication_slot_advance(:slot_name, :lsn)"),
        {"slot_name": REPLICATION_SLOT_NAME, "lsn": lsn},
    )


# 9. Release the advisory lock acquired at task start. This is called in finally to avoid
# lock leaks when errors or retries occur.
def _advisory_unlock(lock_id: int) -> None:
    db.session.execute(text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": lock_id})
