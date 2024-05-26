from app.dao.unsubscribe_request_dao import (
    create_unsubscribe_request_dao,
    get_unsubscribe_request_by_notification_id_dao,
)


def test_create_unsubscribe_request_dao(sample_email_notification):
    create_unsubscribe_request_dao(sample_email_notification)
    unsubscribe_request = get_unsubscribe_request_by_notification_id_dao(sample_email_notification.id)
    assert unsubscribe_request.notification_id == sample_email_notification.id
