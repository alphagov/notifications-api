import uuid
from datetime import datetime, timedelta
from unittest.mock import call

from flask import current_app
from notifications_utils.url_safe_token import generate_token

from app.constants import EMAIL_TYPE
from app.dao.templates_dao import dao_update_template
from app.dao.unsubscribe_request_dao import get_unsubscribe_request_by_notification_id_dao, \
    create_unsubscribe_request_dao
from app.one_click_unsubscribe.rest import is_duplicate_unsubscribe_request
from app.utils import midnight_n_days_ago
from tests.app.db import create_notification, create_template, create_unsubscribe_request_report


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


def test_is_duplicate_unsubscribe_request_for_non_duplicate_request_1(sample_service):
    # Test case is when the notification_id does not exist in the unsubscribe_request table
    result = is_duplicate_unsubscribe_request('9d328a7a-d3f4-4494-a429-63525e7338f4')
    assert result is False


def test_is_duplicate_unsubscribe_request_for_non_duplicate_request_2(sample_service):
    # Test case is an unsubscribe request that has the same notification_id as a previous request
    # that has been processed by the service. Only sequential unprocessed unsubscribe requests with the same
    # notification_id are being considered as duplicate requests.
    template = create_template(service=sample_service, template_type="email")
    notification = create_notification(
        template=template,
        to_field="example@example.com",
        sent_at=datetime.now() - timedelta(days=5),
    )
    # Create processed unsubscribe request report
    unsubscribe_request_report = create_unsubscribe_request_report(
        sample_service,
        earliest_timestamp=midnight_n_days_ago(3),
        latest_timestamp=midnight_n_days_ago(1),
        processed_by_service_at=midnight_n_days_ago(1),
    )
    # Create a processed unsubscribe request
    unsubscribe_request = create_unsubscribe_request_dao(
        {
            "notification_id": notification.id,
            "template_id": notification.template_id,
            "template_version": notification.template_version,
            "service_id": sample_service.id,
            "email_address": notification.to,
            "created_at": midnight_n_days_ago(2),
            "unsubscribe_request_report_id": unsubscribe_request_report.id,
        }
    )
    # Simulate a duplicate unsubscribe request with the same notification_id
    result = is_duplicate_unsubscribe_request(notification.id)
    assert result is False


def test_is_duplicate_unsubscribe_request_for_unbatched_request(sample_service):
    template = create_template(service=sample_service, template_type="email")
    notification = create_notification(
        template=template,
        to_field="example@example.com",
        sent_at=datetime.now() - timedelta(days=4),
    )
    # Create an unsubscribe request
    unsubscribe_request_1 = create_unsubscribe_request_dao(
        {
            "notification_id": notification.id,
            "template_id": notification.template_id,
            "template_version": notification.template_version,
            "service_id": sample_service.id,
            "email_address": notification.to,
            "created_at": datetime.now(),
            "unsubscribe_request_report_id": None,
        }
    )
    # Simulate a duplicate unsubscribe request with the same notification_id
    result = is_duplicate_unsubscribe_request(notification.id)
    assert result is True


def test_is_duplicate_unsubscribe_request_for_batched_unprocessed_request(sample_service):
    template = create_template(service=sample_service, template_type="email")
    notification = create_notification(
        template=template,
        to_field="example@example.com",
        sent_at=datetime.now() - timedelta(days=4),
    )
    # Create processed unsubscribe request report
    unsubscribe_request_report = create_unsubscribe_request_report(
        sample_service,
        earliest_timestamp=midnight_n_days_ago(4),
        latest_timestamp=midnight_n_days_ago(2),
        processed_by_service_at=midnight_n_days_ago(1),
    )
    # Create an unsubscribe request
    unsubscribe_request_1 = create_unsubscribe_request_dao(
        {
            "notification_id": notification.id,
            "template_id": notification.template_id,
            "template_version": notification.template_version,
            "service_id": sample_service.id,
            "email_address": notification.to,
            "created_at": datetime.now(),
            "unsubscribe_request_report_id": unsubscribe_request_report.id,
        }
    )
    # Simulate a duplicate unsubscribe request with the same notification_id
    result = is_duplicate_unsubscribe_request(notification.id)
    assert result is True
