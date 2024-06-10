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
    assert created_unsubscribe_request.template_id == sample_email_notification.template_id
    assert created_unsubscribe_request.template_version == sample_email_notification.template_version
    assert created_unsubscribe_request.service_id == sample_email_notification.service_id
    assert created_unsubscribe_request.email_address == sample_email_notification.to


def test_valid_one_click_unsubscribe_url_after_data_retention_period(client, sample_notification_history):
    token = generate_token("foo@bar.com", current_app.config["SECRET_KEY"], current_app.config["DANGEROUS_SALT"])
    response = unsubscribe_url_post(client, sample_notification_history.id, token)
    response_json_data = response.get_json()
    created_unsubscribe_request = get_unsubscribe_request_by_notification_id_dao(sample_notification_history.id)
    assert response.status_code == 200
    assert response_json_data["message"] == "Unsubscribe successful"
    assert response_json_data["result"] == "success"
    assert created_unsubscribe_request.notification_id == sample_notification_history.id
    assert created_unsubscribe_request.template_id == sample_notification_history.template_id
    assert created_unsubscribe_request.template_version == sample_notification_history.template_version
    assert created_unsubscribe_request.service_id == sample_notification_history.service_id
    assert created_unsubscribe_request.email_address == "foo@bar.com"


def test_invalid_one_click_unsubscribe_url_token(client, sample_email_notification):
    invalid_token = uuid.uuid4()
    response = unsubscribe_url_post(client, sample_email_notification.id, invalid_token)
    response_json_data = response.get_json()
    assert response.status_code == 404
    assert response_json_data["message"] == {"unsubscribe request": "This is not a valid unsubscribe link."}


def test_invalid_one_click_unsubscribe_url_notification_id(client, sample_email_notification):
    invalid_notification_id = uuid.uuid4()
    token = generate_token(
        sample_email_notification.to, current_app.config["SECRET_KEY"], current_app.config["DANGEROUS_SALT"]
    )
    response = unsubscribe_url_post(client, invalid_notification_id, token)
    response_json_data = response.get_json()
    assert response.status_code == 404
    assert response_json_data["message"] == {"unsubscribe request": "This is not a valid unsubscribe link."}
