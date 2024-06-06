import uuid

from flask import current_app
from notifications_utils.url_safe_token import generate_token

from app.dao.unsubscribe_request_dao import get_unsubscribe_request_by_notification_id_dao


def unsubscribe_url_post(client, notification_id, token):
    return client.post(path=f"/unsubscribe/{notification_id}/{token}")


def test_valid_one_click_unsubscribe_url(client, sample_email_notification):
    token = generate_token(
        sample_email_notification.to, current_app.config["SECRET_KEY"], current_app.config["DANGEROUS_SALT"]
    )
    response = unsubscribe_url_post(client, sample_email_notification.id, token)
    response_json_data = response.get_json()
    created_unsubscribe_request = get_unsubscribe_request_by_notification_id_dao(sample_email_notification.id)
    assert response.status_code == 200
    assert response_json_data["message"] == "Unsubscribe successful"
    assert response_json_data["result"] == "success"
    assert created_unsubscribe_request.notification_id == sample_email_notification.id


def test_invalid_one_click_unsubscribe_url(client, sample_email_notification):
    token = uuid.uuid4()
    response = unsubscribe_url_post(client, sample_email_notification.id, token)
    response_json_data = response.get_json()
    assert response.status_code == 400
    assert response_json_data["message"] == {"unsubscribe request": "This is not a valid unsubscribe link."}
