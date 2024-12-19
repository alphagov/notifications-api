import uuid
from unittest.mock import call

import pytest
from flask import current_app
from notifications_utils.url_safe_token import generate_token

from app.constants import EMAIL_TYPE
from app.dao.templates_dao import dao_update_template
from app.dao.unsubscribe_request_dao import get_unsubscribe_request_by_notification_id_dao
from app.models import UnsubscribeRequest
from app.one_click_unsubscribe.rest import is_duplicate_unsubscribe_request
from tests.app.db import create_notification, create_template, create_unsubscribe_request_and_return_the_notification_id


def unsubscribe_url_post(client, notification_id, token):
    return client.post(path=f"/unsubscribe/{notification_id}/{token}")


def test_valid_one_click_unsubscribe_url(mocker, client, sample_email_notification):
    mock_redis = mocker.patch("app.one_click_unsubscribe.rest.redis_store.delete")
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
    assert mock_redis.call_args_list == [
        call(f"service-{sample_email_notification.service.id}-unsubscribe-request-statistics"),
        call(f"service-{sample_email_notification.service.id}-unsubscribe-request-reports-summary"),
    ]


def test_duplicate_unsubscribe_requests(mocker, client, sample_email_notification):
    token = generate_token(
        sample_email_notification.to, current_app.config["SECRET_KEY"], current_app.config["DANGEROUS_SALT"]
    )
    # first unsubscribe request
    unsubscribe_url_post(client, sample_email_notification.id, token)
    # duplicate unsubscribe request
    unsubscribe_url_post(client, sample_email_notification.id, token)

    result = UnsubscribeRequest.query.filter_by(notification_id=sample_email_notification.id).all()

    # The duplicate unsubscribe request shouldn't be added to the unsubscribe_request table
    assert len(result) == 1


def test_unsubscribe_request_object_refers_to_correct_template_version_after_template_updated(client, sample_service):
    test_template = create_template(
        sample_service,
        template_type=EMAIL_TYPE,
    )
    notification = create_notification(template=test_template, to_field="foo@bar.com")
    initial_template_version = test_template.version
    token = generate_token(notification.to, current_app.config["SECRET_KEY"], current_app.config["DANGEROUS_SALT"])

    # update template content to generate new template version
    test_template.content = "New content"
    test_template.process_type = "priority"
    dao_update_template(test_template)
    subsequent_template_version = test_template.version

    response = unsubscribe_url_post(client, notification.id, token)

    created_unsubscribe_request = get_unsubscribe_request_by_notification_id_dao(notification.id)
    assert response.status_code == 200
    assert created_unsubscribe_request.template_version != subsequent_template_version
    assert created_unsubscribe_request.template_version == initial_template_version
    assert created_unsubscribe_request.template_id == test_template.id


def test_unsubscribe_request_object_refers_to_correct_template_version_after_template_is_archived(
    client, sample_service
):
    test_template = create_template(
        sample_service,
        template_type=EMAIL_TYPE,
    )
    initial_template_version = test_template.version
    notification = create_notification(template=test_template, to_field="foo@bar.com")
    token = generate_token(notification.to, current_app.config["SECRET_KEY"], current_app.config["DANGEROUS_SALT"])

    # archive template
    test_template.archived = True
    dao_update_template(test_template)
    subsequent_template_version = test_template.version

    response = unsubscribe_url_post(client, notification.id, token)

    created_unsubscribe_request = get_unsubscribe_request_by_notification_id_dao(notification.id)

    assert response.status_code == 200
    assert created_unsubscribe_request.template_version != subsequent_template_version
    assert created_unsubscribe_request.template_version == initial_template_version
    assert created_unsubscribe_request.template_id == test_template.id
    assert created_unsubscribe_request.email_address == notification.to


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


@pytest.mark.parametrize(
    "create_previous_unsubscribe_request,is_batched, processed_by_service, expected_result",
    [(False, False, False, False), (True, True, True, False), (True, False, False, True), (True, True, False, True)],
)
def test_is_duplicate_unsubscribe_request(
    sample_service,
    sample_email_template,
    create_previous_unsubscribe_request,
    is_batched,
    processed_by_service,
    expected_result,
):
    if create_previous_unsubscribe_request:
        notification_id = create_unsubscribe_request_and_return_the_notification_id(
            sample_service, sample_email_template, is_batched, processed_by_service
        )
    else:
        notification_id = uuid.uuid4()

    result = is_duplicate_unsubscribe_request(notification_id)
    assert result == expected_result
