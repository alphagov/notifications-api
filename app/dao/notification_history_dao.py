from app.models import NotificationHistory


def get_notification_history_by_id(notification_history_id):
    return NotificationHistory.query.filter_by(id=notification_history_id).one_or_none()
