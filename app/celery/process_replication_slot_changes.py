from uuid import UUID

from app import current_app, db, notify_celery
from app.cronitor import cronitor
from app.dao.service_stats_dao import (
    ServiceStatsDimensions,
    apply_service_stats_delete,
    apply_service_stats_insert,
    apply_service_stats_update_transition,
)
from app.replication.replication_changes_utils import (
    ParsedRow,
    RowData,
    get_notification_status,
    get_replication_changes,
    get_str_value,
)


def _parse_uuid_value(row_data: RowData, key: str) -> UUID | None:
    raw_value = get_str_value(row_data, key)
    if not raw_value:
        return None

    try:
        return UUID(raw_value)
    except ValueError:
        return None


def _build_dimensions(change: ParsedRow, *, use_previous_row: bool) -> ServiceStatsDimensions | None:
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
    notification_status = get_notification_status(row_data) or get_notification_status(fallback_data)

    if not service_id or not template_id or not notification_type or not notification_status:
        return None

    return {
        "service_id": service_id,
        "template_id": template_id,
        "notification_type": notification_type,
        "notification_status": notification_status,
    }


def _build_old_dimensions_from_previous_status(change: ParsedRow) -> ServiceStatsDimensions | None:
    current_dimensions = _build_dimensions(change, use_previous_row=False)
    if not current_dimensions:
        return None

    previous_status = get_notification_status(change["previous_row_data"])
    if not previous_status:
        return None

    return {
        "service_id": current_dimensions["service_id"],
        "template_id": current_dimensions["template_id"],
        "notification_type": current_dimensions["notification_type"],
        "notification_status": previous_status,
    }


# @TODO: this is a temporary task to check the replication slot changes,
# we will need to implement the logic to process the changes and update the dashboard accordingly
@notify_celery.task(bind=True, name="check-replication-slot-changes")
@cronitor("check-replication-slot-changes")
def check_replication_slot_changes(self):
    try:
        changes = get_replication_changes(peek=False)

        if not changes:
            current_app.logger.info(
                "No replication slot changes found",
                extra={"celery_task": "check-replication-slot-changes", "changes_count": 0},
            )
            return

        processed_changes = 0
        ignored_changes = 0

        for change in changes:
            if change["table"] != "notifications":
                ignored_changes += 1
                continue

            change_type = change["type"]
            if change_type == "insert":
                dimensions = _build_dimensions(change, use_previous_row=False)
                if not dimensions:
                    ignored_changes += 1
                    continue
                apply_service_stats_insert(dimensions)
                processed_changes += 1
                continue

            if change_type == "delete":
                dimensions = _build_dimensions(change, use_previous_row=False)
                if not dimensions:
                    ignored_changes += 1
                    continue
                apply_service_stats_delete(dimensions)
                processed_changes += 1
                continue

            if change_type == "update":
                new_dimensions = _build_dimensions(change, use_previous_row=False)
                if not new_dimensions:
                    ignored_changes += 1
                    continue

                old_dimensions = _build_old_dimensions_from_previous_status(change)
                if old_dimensions:
                    apply_service_stats_update_transition(old_dimensions, new_dimensions)
                else:
                    apply_service_stats_insert(new_dimensions)

                processed_changes += 1
                continue

            ignored_changes += 1

        current_app.logger.info(
            "Replication slot changes processed",
            extra={
                "celery_task": "check-replication-slot-changes",
                "changes_count": len(changes),
                "processed_changes": processed_changes,
                "ignored_changes": ignored_changes,
            },
        )

        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        retry_count = self.request.retries
        if retry_count < 3:
            raise self.retry(exc=exc, countdown=2**retry_count) from exc
        else:
            current_app.logger.error(
                "Replication slot query failed after 3 retries",
                exc_info=True,
                extra={"celery_task": "check-replication-slot-changes"},
            )
            raise
