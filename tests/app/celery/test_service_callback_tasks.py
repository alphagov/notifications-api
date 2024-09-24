import json
import uuid
from datetime import datetime
from unittest import mock

import pytest
import requests_mock
from freezegun import freeze_time
from requests import RequestException
from sqlalchemy.exc import SQLAlchemyError

from app import signing
from app.celery.service_callback_tasks import (
    _send_data_to_service_callback_api,
    send_complaint_to_service,
    send_delivery_status_to_service,
    send_inbound_sms_to_service,
)
from app.utils import DATETIME_FORMAT
from tests.app.db import (
    create_complaint,
    create_inbound_sms,
    create_notification,
    create_service,
    create_service_callback_api,
    create_service_inbound_api,
    create_template,
)


def _set_up_test_data(notification_type, callback_type):
    service = create_service(restricted=True)
    template = create_template(service=service, template_type=notification_type, subject="Hello")
    callback_api = create_service_callback_api(
        service=service,
        url="https://some.service.gov.uk/",
        bearer_token="something_unique",
        callback_type=callback_type,
    )
    return callback_api, template


def _set_up_data_for_status_update(callback_api, notification):
    data = {
        "notification_id": str(notification.id),
        "notification_client_reference": notification.client_reference,
        "notification_to": notification.to,
        "notification_status": notification.status,
        "notification_created_at": notification.created_at.strftime(DATETIME_FORMAT),
        "notification_updated_at": (
            notification.updated_at.strftime(DATETIME_FORMAT) if notification.updated_at else None
        ),
        "notification_sent_at": notification.sent_at.strftime(DATETIME_FORMAT) if notification.sent_at else None,
        "notification_type": notification.notification_type,
        "service_callback_api_url": callback_api.url,
        "service_callback_api_bearer_token": callback_api.bearer_token,
        "template_id": str(notification.template_id),
        "template_version": notification.template_version,
    }
    encoded_status_update = signing.encode(data)
    return encoded_status_update


def _set_up_data_for_complaint(callback_api, complaint, notification):
    data = {
        "complaint_id": str(complaint.id),
        "notification_id": str(notification.id),
        "reference": notification.client_reference,
        "to": notification.to,
        "complaint_date": complaint.complaint_date.strftime(DATETIME_FORMAT),
        "service_callback_api_url": callback_api.url,
        "service_callback_api_bearer_token": callback_api.bearer_token,
    }
    obscured_status_update = signing.encode(data)
    return obscured_status_update


@pytest.mark.parametrize("notification_type", ["email", "sms"])
def test_send_delivery_status_to_service_sends_callback_to_service(notify_db_session, notification_type, mocker):
    callback_api, template = _set_up_test_data(notification_type, "delivery_status")
    datestr = datetime(2017, 6, 20)

    notification = create_notification(
        template=template, created_at=datestr, updated_at=datestr, sent_at=datestr, status="sent"
    )
    encoded_status_update = _set_up_data_for_status_update(callback_api, notification)

    send_callback_mock = mocker.patch("app.celery.service_callback_tasks._send_data_to_service_callback_api")

    send_delivery_status_to_service(notification.id, encoded_status_update=encoded_status_update)

    expected_data = {
        "id": str(notification.id),
        "reference": notification.client_reference,
        "to": notification.to,
        "status": notification.status,
        "created_at": datestr.strftime(DATETIME_FORMAT),
        "completed_at": datestr.strftime(DATETIME_FORMAT),
        "sent_at": datestr.strftime(DATETIME_FORMAT),
        "notification_type": notification_type,
        "template_id": str(template.id),
        "template_version": 1,
    }

    send_callback_mock.assert_called_once_with(
        mock.ANY, expected_data, callback_api.url, callback_api.bearer_token, "send_delivery_status_to_service"
    )


def test_send_complaint_to_service_sends_callback_to_service(notify_db_session, mocker):
    with freeze_time("2001-01-01T12:00:00"):
        callback_api, template = _set_up_test_data("email", "complaint")

        notification = create_notification(template=template)
        complaint = create_complaint(service=template.service, notification=notification)
        complaint_data = _set_up_data_for_complaint(callback_api, complaint, notification)
        send_callback_mock = mocker.patch("app.celery.service_callback_tasks._send_data_to_service_callback_api")

        send_complaint_to_service(complaint_data)

        expected_data = {
            "notification_id": str(notification.id),
            "complaint_id": str(complaint.id),
            "reference": notification.client_reference,
            "to": notification.to,
            "complaint_date": datetime.utcnow().strftime(DATETIME_FORMAT),
        }

        send_callback_mock.assert_called_once_with(
            mock.ANY, expected_data, callback_api.url, callback_api.bearer_token, "send_complaint_to_service"
        )


def test_send_inbound_sms_to_service_sends_callback_to_service(notify_api, sample_service, mocker):
    create_service_inbound_api(
        service=sample_service, url="https://some.service.gov.uk/", bearer_token="something_unique"
    )
    inbound_sms = create_inbound_sms(
        service=sample_service,
        notify_number="0751421",
        user_number="447700900111",
        provider_date=datetime(2017, 6, 20),
        content="Here is some content",
    )
    data = {
        "id": str(inbound_sms.id),
        "source_number": inbound_sms.user_number,
        "destination_number": inbound_sms.notify_number,
        "message": inbound_sms.content,
        "date_received": inbound_sms.provider_date.strftime(DATETIME_FORMAT),
    }

    send_callback_mock = mocker.patch("app.celery.service_callback_tasks._send_data_to_service_callback_api")

    send_inbound_sms_to_service(inbound_sms.id, inbound_sms.service_id)
    send_callback_mock.assert_called_once_with(
        mock.ANY, data, "https://some.service.gov.uk/", "something_unique", "send_inbound_sms_to_service"
    )


def test_send_inbound_sms_to_service_does_not_send_callback_when_inbound_sms_does_not_exist(
    notify_api, sample_service, mocker
):
    create_service_inbound_api(service=sample_service)
    send_callback_mock = mocker.patch("app.celery.service_callback_tasks._send_data_to_service_callback_api")

    with pytest.raises(SQLAlchemyError):
        send_inbound_sms_to_service(inbound_sms_id=uuid.uuid4(), service_id=sample_service.id)

    assert send_callback_mock.call_count == 0


def test_send_inbound_sms_to_service_does_not_sent_callback_when_inbound_api_does_not_exist(
    notify_api, sample_service, mocker
):
    inbound_sms = create_inbound_sms(
        service=sample_service,
        notify_number="0751421",
        user_number="447700900111",
        provider_date=datetime(2017, 6, 20),
        content="Here is some content",
    )
    send_callback_mock = mocker.patch("app.celery.service_callback_tasks._send_data_to_service_callback_api")
    send_inbound_sms_to_service(inbound_sms.id, inbound_sms.service_id)

    assert send_callback_mock.call_count == 0


def test__send_data_to_service_callback_api_posts_https_request_to_service(notify_db_session, mocker):
    data = {"id": "hello"}
    callback_url = "https://www.example.com/callback"
    celery_task_mock = mock.MagicMock()

    with requests_mock.Mocker() as request_mock:
        request_mock.post(callback_url, json={}, status_code=200)
        _send_data_to_service_callback_api(celery_task_mock, data, callback_url, "my-token", "my_function_name")

    assert request_mock.call_count == 1
    assert request_mock.request_history[0].url == callback_url
    assert request_mock.request_history[0].method == "POST"
    assert request_mock.request_history[0].text == json.dumps(data)
    assert request_mock.request_history[0].headers["Content-type"] == "application/json"
    assert request_mock.request_history[0].headers["Authorization"] == "Bearer {}".format("my-token")

    celery_task_mock.retry.assert_not_called()


@pytest.mark.parametrize("status_code", [429, 500, 503])
def test__send_data_to_service_callback_api_retries_if_request_returns_retryable_status_code(
    notify_db_session, mocker, status_code
):
    data = {"id": "hello"}
    callback_url = "https://www.example.com/callback"

    celery_task_mock = mock.MagicMock()

    with requests_mock.Mocker() as request_mock:
        request_mock.post(callback_url, json={}, status_code=status_code)
        _send_data_to_service_callback_api(celery_task_mock, data, callback_url, "my-token", "my_function_name")

    celery_task_mock.retry.assert_called_once_with(queue="service-callbacks-retry")


def test__send_data_to_service_callback_api_retries_if_request_raises_unknown_exception(notify_db_session, mocker):
    data = {"id": "hello"}
    callback_url = "https://www.example.com/callback"

    celery_task_mock = mock.MagicMock()

    mocker.patch("app.celery.service_callback_tasks.requests_session.request", side_effect=RequestException())

    _send_data_to_service_callback_api(celery_task_mock, data, callback_url, "my-token", "my_function_name")

    celery_task_mock.retry.assert_called_once_with(queue="service-callbacks-retry")


@pytest.mark.parametrize("status_code", [403, 404])
def test__send_data_to_service_callback_api_doesnt_retry_if_non_retry_status_code(
    notify_db_session, mocker, status_code
):
    data = {"id": "hello"}
    callback_url = "https://www.example.com/callback"

    celery_task_mock = mock.MagicMock()

    with requests_mock.Mocker() as request_mock:
        request_mock.post(callback_url, json={}, status_code=status_code)
        _send_data_to_service_callback_api(celery_task_mock, data, callback_url, "my-token", "my_function_name")

    celery_task_mock.retry.assert_not_called()


@pytest.mark.parametrize("data", [{"id": "hello"}, {"notification_id": "hello"}])
def test__send_data_to_service_callback_api_handles_data_with_notification_id_or_id(notify_db_session, mocker, data):
    callback_url = "https://www.example.com/callback"

    with requests_mock.Mocker() as request_mock:
        request_mock.post(callback_url, json={}, status_code=200)
        _send_data_to_service_callback_api(mock.MagicMock(), data, callback_url, "my-token", "my_function_name")
