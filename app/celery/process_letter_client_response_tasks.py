from flask import current_app

from app import notify_celery
from app.dao.notifications_dao import dao_get_notification_or_history_by_id


@notify_celery.task(bind=True, name="process-letter-callback")
def process_letter_callback_data(self, notification_id, page_count):
    notification = dao_get_notification_or_history_by_id(notification_id)

    check_billable_units_by_id(notification, page_count)


def check_billable_units_by_id(notification, dvla_page_count):
    if notification.billable_units != int(dvla_page_count):
        current_app.logger.error(
            "Notification with id %s has %s billable_units but DVLA says page count is %s",
            notification.id,
            notification.billable_units,
            dvla_page_count,
        )
