from flask import current_app

from app import db
from app.models import NotificationHistory


def delete_notification_history_between_two_datetimes(start, end):
    # start time is inclusive, end time is exclusive
    current_app.logger.info("Beginning to delete notification_history between %s and %s", start, end)

    num_rows_deleted = NotificationHistory.query.filter(
        NotificationHistory.created_at >= start, NotificationHistory.created_at < end
    ).delete(synchronize_session=False)

    db.session.commit()

    current_app.logger.info(
        "Finishing deleting %s rows of notification_history between %s and %s", num_rows_deleted, start, end
    )
