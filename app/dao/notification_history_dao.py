from flask import current_app

from app import db


def delete_notification_history_older_than_datetime(older_than_datetime, query_limit=50000):
    current_app.logger.info("Beginning to delete notification_history older than %s", older_than_datetime)

    # We want to run this function concurrently, ie having several workers running this same task at the same time
    # To ensure workers don't try and delete the same notifications (which will cause them to stop and exit)
    # we get them to pick a random sample of notifications
    # In production, to get 50,000 results we only need a random sample of about 0.05% of the table to give us
    # 50,000 rows
    # However, in other environments, including test, we don't have many notifications in the notification_history
    # table and therefore need to get all of them (and don't need to worry about performance)
    if current_app.config["NOTIFY_ENVIRONMENT"] == "production":
        tablesample_percentage = 0.05
    else:
        tablesample_percentage = 100

    total_deleted = 0
    deleted_this_iteration = 1
    while deleted_this_iteration > 0:
        delete_query = f"""
            DELETE FROM notification_history
            where id in (
                select id from notification_history TABLESAMPLE SYSTEM ({tablesample_percentage})
                where created_at < '{older_than_datetime}'
                limit {query_limit}
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
