from datetime import datetime

from app.dao.notification_history_dao import (
    delete_notification_history_between_two_datetimes,
)
from app.models import NotificationHistory
from tests.app.db import create_notification_history


def test_delete_notification_history_between_two_datetimes(notify_db_session, sample_letter_template):
    notification_history_datetimes = [
        datetime(2022, 2, 6, 13, 0, 0),
        datetime(2022, 2, 7, 12, 59, 59),
        datetime(2022, 2, 7, 13, 0, 0),
        datetime(2022, 2, 7, 13, 0, 1),
        datetime(2022, 2, 7, 13, 7, 0),
        datetime(2022, 2, 7, 13, 42, 8),
        datetime(2022, 2, 7, 13, 59, 59),
        datetime(2022, 2, 7, 14, 0, 0),
        datetime(2022, 2, 7, 14, 0, 1),
        datetime(2022, 2, 8, 13, 0, 0),
    ]
    for dt in notification_history_datetimes:
        create_notification_history(
            sample_letter_template, status="delivered", created_at=dt, sent_at=dt, updated_at=dt
        )
    notification_history_rows = NotificationHistory.query.order_by(NotificationHistory.created_at).all()
    assert len(notification_history_rows) == 10

    delete_notification_history_between_two_datetimes(datetime(2022, 2, 7, 13, 0, 0), datetime(2022, 2, 7, 14, 0, 0))

    notification_history_rows = NotificationHistory.query.order_by(NotificationHistory.created_at).all()
    assert len(notification_history_rows) == 5

    assert notification_history_rows[0].created_at == notification_history_datetimes[0]
    assert notification_history_rows[1].created_at == notification_history_datetimes[1]
    assert notification_history_rows[2].created_at == notification_history_datetimes[7]
    assert notification_history_rows[3].created_at == notification_history_datetimes[8]
    assert notification_history_rows[4].created_at == notification_history_datetimes[9]
