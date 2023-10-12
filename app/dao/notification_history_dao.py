from flask import current_app
from sqlalchemy import select

from app import db
from app.models import NotificationHistory


def delete_notification_history_older_than_datetime(older_than_datetime, query_limit=50000):
    current_app.logger.info("Beginning to delete notification_history older than %s", older_than_datetime)

    total_deleted = 0
    deleted_this_iteration = 1
    while deleted_this_iteration > 0:
        notification_ids_to_delete = (
            select(NotificationHistory.id)
            .where(NotificationHistory.created_at < older_than_datetime)
            .limit(query_limit)
        )

        current_app.logger.info("Found chunk of rows from notification_history to delete")

        num_rows_deleted = NotificationHistory.query.filter(
            NotificationHistory.id.in_(notification_ids_to_delete),
        ).delete(synchronize_session=False)

        current_app.logger.info("Deleted chunk of %s rows from notification_history", num_rows_deleted)

        deleted_this_iteration = num_rows_deleted
        total_deleted += num_rows_deleted

        db.session.commit()

    current_app.logger.info(
        "Deleted %s rows from notification_history older than %s", total_deleted, older_than_datetime
    )


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
