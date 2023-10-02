from datetime import datetime

from app.dao.notification_history_dao import delete_notification_history_older_than_datetime
from app.models import NotificationHistory
from tests.app.db import create_notification_history


def test_delete_notification_history_older_than_datetime(notify_db_session, sample_letter_template):
    notification_history_datetimes = [
        datetime(2022, 2, 7),
        datetime(2022, 6, 29),
        datetime(2022, 6, 30, 23, 59, 59),
        datetime(2022, 7, 1),
        datetime(2023, 9, 4),
    ]
    for dt in notification_history_datetimes:
        create_notification_history(
            sample_letter_template, status="delivered", created_at=dt, sent_at=dt, updated_at=dt
        )
    notification_history_rows = NotificationHistory.query.order_by(NotificationHistory.created_at).all()
    assert len(notification_history_rows) == 5
    assert notification_history_rows[0].created_at == datetime(2022, 2, 7)

    delete_notification_history_older_than_datetime(datetime(2022, 7, 1), query_limit=1)

    notification_history_rows = NotificationHistory.query.order_by(NotificationHistory.created_at).all()
    assert len(notification_history_rows) == 2
    assert notification_history_rows[0].created_at == datetime(2022, 7, 1)
