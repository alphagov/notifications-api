from flask import current_app

from app.dao.dao_utils import autocommit
from app.models import NotificationHistory


@autocommit
def delete_notification_history_older_than_datetime(older_than_datetime):
    current_app.logger.info("Beginning to delete notification_history older than %s", older_than_datetime)

    num_rows_deleted = NotificationHistory.query.filter(
        NotificationHistory.created_at < older_than_datetime,
    ).delete()

    current_app.logger.info(
        "Deleted %s rows from notification_history older than %s", num_rows_deleted, older_than_datetime
    )
