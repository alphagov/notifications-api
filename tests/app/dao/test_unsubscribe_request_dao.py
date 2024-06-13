from app.dao.unsubscribe_request_dao import (
    create_unsubscribe_request_dao,
    get_unsubscribe_request_by_notification_id_dao,
)
from app.one_click_unsubscribe.rest import get_unsubscribe_request_data


def test_create_unsubscribe_request_dao(sample_email_notification):
    email_address = "foo@bar"
    unsubscribe_data = get_unsubscribe_request_data(sample_email_notification, email_address)
    create_unsubscribe_request_dao(unsubscribe_data)
    unsubscribe_request = get_unsubscribe_request_by_notification_id_dao(sample_email_notification.id)
    assert unsubscribe_request.notification_id == sample_email_notification.id
    assert unsubscribe_request.email_address == email_address
    assert unsubscribe_request.template_id == sample_email_notification.template_id
    assert unsubscribe_request.template_version == sample_email_notification.template_version
    assert unsubscribe_request.service_id == sample_email_notification.service_id
