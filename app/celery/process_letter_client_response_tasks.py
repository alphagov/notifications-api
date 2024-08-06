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
    # decide what to do with duplicate updates

    notification = dao_get_notification_or_history_by_id(notification_id)

    check_billable_units_by_id(notification, page_count)

    if dvla_status == DVLA_NOTIFICATION_DISPATCHED:
        status = NOTIFICATION_DELIVERED
    else:
        status = NOTIFICATION_TECHNICAL_FAILURE

    notification.status = status

    dao_update_notification(notification)

    if status == NOTIFICATION_TECHNICAL_FAILURE:
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
