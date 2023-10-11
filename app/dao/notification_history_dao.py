from flask import current_app

from app import db


def delete_notification_history_older_than_datetime(older_than_datetime, query_limit=50000):
    current_app.logger.info("Beginning to delete notification_history older than %s", older_than_datetime)

    total_deleted = 0
    deleted_this_iteration = 1
    while deleted_this_iteration > 0:
        delete_query = f"""
            DELETE FROM notification_history
            where id in (
                select id from notification_history where created_at < '{older_than_datetime}' limit {query_limit}
            )
        """

        num_rows_deleted = db.session.execute(delete_query).rowcount
        db.session.commit()
        deleted_this_iteration = num_rows_deleted
        total_deleted += num_rows_deleted

        current_app.logger.info("Deleted chunk of %s rows from notification_history", num_rows_deleted)

    current_app.logger.info(
        "Deleted %s rows from notification_history older than %s", total_deleted, older_than_datetime
    )
