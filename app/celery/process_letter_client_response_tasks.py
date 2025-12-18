import uuid
from datetime import date

from flask import current_app

from app import notify_celery
from app.constants import (
    DVLA_NOTIFICATION_REJECTED,
    DVLA_TO_NOTIFICATION_STATUS_MAP,
    NOTIFICATION_TECHNICAL_FAILURE,
)
from app.dao.notifications_dao import (
    _duplicate_update_warning,
    dao_get_notification_or_history_by_id,
    dao_record_letter_despatched_on_by_id,
    dao_update_notification,
)
from app.exceptions import NotificationTechnicalFailureException
from app.models import LetterCostThreshold


@notify_celery.task(bind=True, name="process-letter-callback")
def process_letter_callback_data(
    self,
    notification_id: uuid.UUID,
    page_count: int | None,
    dvla_status: str,
    cost_threshold: str | None,
    despatch_date: date,
):
    notification = dao_get_notification_or_history_by_id(notification_id)

    if dvla_status != DVLA_NOTIFICATION_REJECTED:
        validate_billable_units(notification, page_count)

    new_status = determine_new_status(dvla_status)

    already_updated_status = set(DVLA_TO_NOTIFICATION_STATUS_MAP.values())

    if notification.status in already_updated_status:
        _duplicate_update_warning(notification, new_status)
        return

    notification.status = new_status

    dao_update_notification(notification)

    if new_status == NOTIFICATION_TECHNICAL_FAILURE:
        raise NotificationTechnicalFailureException(
            f"Letter status received as REJECTED for notification id: {notification.id}"
        )

    if cost_threshold is not None:
        cost_threshold = LetterCostThreshold(cost_threshold)
        dao_record_letter_despatched_on_by_id(notification_id, despatch_date, cost_threshold)


def validate_billable_units(notification, dvla_page_count):
    if notification.billable_units != int(dvla_page_count):
        extra = {
            "notification_id": notification.id,
            "notification_billable_units": notification.billable_units,
            "page_count": dvla_page_count,
        }
        current_app.logger.error(
            "Notification with id %(notification_id)s has %(notification_billable_units)s billable_units but "
            "DVLA says page count is %(page_count)s",
            extra,
            extra=extra,
        )


def determine_new_status(dvla_status):
    return DVLA_TO_NOTIFICATION_STATUS_MAP[dvla_status]
