from flask import current_app

from app import db
from app.models import NotificationHistory


def delete_notification_history_between_two_datetimes(start: str, end: str):
    # start time is inclusive, end time is exclusive

    extra = {
        "start_time": start,
        "end_time": end,
    }
    current_app.logger.info(
        "Beginning to delete notification_history between %(start_time)s and %(end_time)s", extra, extra=extra
    )

    num_rows_deleted = NotificationHistory.query.filter(
        NotificationHistory.created_at >= start, NotificationHistory.created_at < end
    ).delete(synchronize_session=False)

    db.session.commit()

    extra = {
        **extra,
        "deleted_record_count": num_rows_deleted,
    }
    current_app.logger.info(
        "Finished deleting %(deleted_record_count)s rows of notification_history "
        "between %(start_time)s and %(end_time)s",
        extra,
        extra=extra,
    )


def get_notification_history_by_id(notification_history_id):
    return NotificationHistory.query.filter_by(id=notification_history_id).one_or_none()
