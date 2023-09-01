from flask import current_app

from app.models import NotificationHistory


def delete_notification_history_older_than_datetime(older_than_datetime):
    current_app.logger.info("Beginning to delete notification_history older than %s", older_than_datetime)

    num_rows_deleted = NotificationHistory.query.filter(
        NotificationHistory.sent_at < older_than_datetime,
    ).delete()

    current_app.logger.info(
        "Deleted %s rows from notification_history older than %s", num_rows_deleted, older_than_datetime
    )
