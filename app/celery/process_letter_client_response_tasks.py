from flask import current_app

from app import notify_celery
from app.constants import DVLA_NOTIFICATION_DISPATCHED, NOTIFICATION_DELIVERED, NOTIFICATION_TECHNICAL_FAILURE
from app.dao.notifications_dao import (
    dao_get_notification_or_history_by_id,
    dao_update_notification,
)
from app.exceptions import NotificationTechnicalFailureException


@notify_celery.task(bind=True, name="process-letter-callback")
def process_letter_callback_data(self, notification_id, page_count, dvla_status):
    notification = dao_get_notification_or_history_by_id(notification_id)

    check_billable_units_by_id(notification, page_count)

    new_status = determine_new_status(dvla_status)

    if is_duplicate_update(notification.status, new_status):
        current_app.logger.info(
            "Duplicate update received for notification id: %s with status: %s",
            notification_id,
            new_status,
        )
        return

    notification.status = new_status

    dao_update_notification(notification)

    if new_status == NOTIFICATION_TECHNICAL_FAILURE:
        raise NotificationTechnicalFailureException(
            f"Letter status received as REJECTED for notification id: {notification.id}"
        )


def check_billable_units_by_id(notification, dvla_page_count):
    if notification.billable_units != int(dvla_page_count):
        current_app.logger.error(
            "Notification with id %s has %s billable_units but DVLA says page count is %s",
            notification.id,
            notification.billable_units,
            dvla_page_count,
        )


def determine_new_status(dvla_status):
    if dvla_status == DVLA_NOTIFICATION_DISPATCHED:
        return NOTIFICATION_DELIVERED

    return NOTIFICATION_TECHNICAL_FAILURE


def is_duplicate_update(current_status, new_status):
    return new_status == current_status
