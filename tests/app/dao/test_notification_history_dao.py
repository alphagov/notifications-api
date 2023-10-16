from app.dao.notification_history_dao import (
    delete_notification_history_between_two_datetimes,
)
from app.models import NotificationHistory
from tests.app.db import create_notification_history


def test_delete_notification_history_between_two_datetimes(notify_db_session, sample_letter_template):
    notification_history_datetimes = [
        "2022-02-06T13:00:00",
        "2022-02-07T12:59:59",
        "2022-02-07T13:00:00",
        "2022-02-07T13:00:01",
        "2022-02-07T13:07:00",
        "2022-02-07T13:42:08",
        "2022-02-07T13:59:59",
        "2022-02-07T14:00:00",
        "2022-02-07T14:00:01",
        "2022-02-08T13:00:00",
    ]
    for dt in notification_history_datetimes:
        create_notification_history(
            sample_letter_template, status="delivered", created_at=dt, sent_at=dt, updated_at=dt
        )
    notification_history_rows = NotificationHistory.query.order_by(NotificationHistory.created_at).all()
    assert len(notification_history_rows) == 10

    delete_notification_history_between_two_datetimes("2022-02-07T13:00:00", "2022-02-07T14:00:00")

    notification_history_rows = NotificationHistory.query.order_by(NotificationHistory.created_at).all()
    assert len(notification_history_rows) == 5

    assert notification_history_rows[0].created_at.isoformat() == notification_history_datetimes[0]
    assert notification_history_rows[1].created_at.isoformat() == notification_history_datetimes[1]
    assert notification_history_rows[2].created_at.isoformat() == notification_history_datetimes[7]
    assert notification_history_rows[3].created_at.isoformat() == notification_history_datetimes[8]
    assert notification_history_rows[4].created_at.isoformat() == notification_history_datetimes[9]
