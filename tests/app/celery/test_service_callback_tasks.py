import uuid
import json
from datetime import datetime

from requests import RequestException
import pytest
import requests_mock
from sqlalchemy.exc import SQLAlchemyError

from app import (DATETIME_FORMAT, encryption)

from tests.app.db import (
    create_notification,
    create_service_callback_api,
    create_service,
    create_template
)
from app.celery.service_callback_tasks import send_delivery_status_to_service
from app.config import QueueNames


@pytest.mark.parametrize("notification_type",
                         ["email", "letter", "sms"])
def test_send_delivery_status_to_service_post_https_request_to_service_with_encrypted_data(
        notify_db_session, notification_type):

    callback_api, template = _set_up_test_data(notification_type)
    datestr = datetime(2017, 6, 20)

    notification = create_notification(template=template,
                                       created_at=datestr,
                                       updated_at=datestr,
                                       sent_at=datestr,
                                       status='sent'
                                       )
    encrypted_status_update = _set_up_encrypted_data(callback_api, notification)
    with requests_mock.Mocker() as request_mock:
        request_mock.post(callback_api.url,
                          json={},
                          status_code=200)
        send_delivery_status_to_service(notification.id, encrypted_status_update=encrypted_status_update)

    mock_data = {
        "id": str(notification.id),
        "reference": notification.client_reference,
        "to": notification.to,
        "status": notification.status,
        "created_at": datestr.strftime(DATETIME_FORMAT),
        "completed_at": datestr.strftime(DATETIME_FORMAT),
        "sent_at": datestr.strftime(DATETIME_FORMAT),
        "notification_type": notification_type
    }

    assert request_mock.call_count == 1
    assert request_mock.request_history[0].url == callback_api.url
    assert request_mock.request_history[0].method == 'POST'
    assert request_mock.request_history[0].text == json.dumps(mock_data)
    assert request_mock.request_history[0].headers["Content-type"] == "application/json"
    assert request_mock.request_history[0].headers["Authorization"] == "Bearer {}".format(callback_api.bearer_token)


@pytest.mark.parametrize("notification_type",
                         ["email", "letter", "sms"])
def test_send_delivery_status_to_service_retries_if_request_returns_500_with_encrypted_data(
        notify_db_session, mocker, notification_type
):
    callback_api, template = _set_up_test_data(notification_type)
    datestr = datetime(2017, 6, 20)
    notification = create_notification(template=template,
                                       created_at=datestr,
                                       updated_at=datestr,
                                       sent_at=datestr,
                                       status='sent'
                                       )
    encrypted_data = _set_up_encrypted_data(callback_api, notification)
    mocked = mocker.patch('app.celery.service_callback_tasks.send_delivery_status_to_service.retry')
    with requests_mock.Mocker() as request_mock:
        request_mock.post(callback_api.url,
                          json={},
                          status_code=500)
        send_delivery_status_to_service(notification.id, encrypted_status_update=encrypted_data)

    assert mocked.call_count == 1
    assert mocked.call_args[1]['queue'] == 'retry-tasks'


@pytest.mark.parametrize("notification_type",
                         ["email", "letter", "sms"])
def test_send_delivery_status_to_service_does_not_retries_if_request_returns_404_with_encrypted_data(
        notify_db_session,
        mocker,
        notification_type
):
    callback_api, template = _set_up_test_data(notification_type)
    datestr = datetime(2017, 6, 20)
    notification = create_notification(template=template,
                                       created_at=datestr,
                                       updated_at=datestr,
                                       sent_at=datestr,
                                       status='sent'
                                       )
    encrypted_data = _set_up_encrypted_data(callback_api, notification)
    mocked = mocker.patch('app.celery.service_callback_tasks.send_delivery_status_to_service.retry')
    with requests_mock.Mocker() as request_mock:
        request_mock.post(callback_api.url,
                          json={},
                          status_code=404)
        send_delivery_status_to_service(notification.id, encrypted_status_update=encrypted_data)

    assert mocked.call_count == 0


def _set_up_test_data(notification_type):
    service = create_service(restricted=True)
    template = create_template(service=service, template_type=notification_type, subject='Hello')
    callback_api = create_service_callback_api(service=service, url="https://some.service.gov.uk/",
                                               bearer_token="something_unique")
    return callback_api, template


def _set_up_encrypted_data(callback_api, notification):
    data = {
        "notification_id": str(notification.id),
        "notification_client_reference": notification.client_reference,
        "notification_to": notification.to,
        "notification_status": notification.status,
        "notification_created_at": notification.created_at.strftime(DATETIME_FORMAT),
        "notification_updated_at": notification.updated_at.strftime(DATETIME_FORMAT),
        "notification_sent_at": notification.sent_at.strftime(DATETIME_FORMAT),
        "notification_type": notification.notification_type,
        "service_callback_api_url": callback_api.url,
        "service_callback_api_bearer_token": callback_api.bearer_token,
    }
    encrypted_status_update = encryption.encrypt(data)
    return encrypted_status_update


# We are updating the task to take everything it needs so that there are no db calls.
# The following tests will be deleted once that is complete.
@pytest.mark.parametrize("notification_type",
                         ["email", "letter", "sms"])
def test_send_delivery_status_to_service_post_https_request_to_service(
        notify_db_session, notification_type):
    callback_api, template = _set_up_test_data(notification_type)
    datestr = datetime(2017, 6, 20)

    notification = create_notification(template=template,
                                       created_at=datestr,
                                       updated_at=datestr,
                                       sent_at=datestr,
                                       status='sent'
                                       )

    with requests_mock.Mocker() as request_mock:
        request_mock.post(callback_api.url,
                          json={},
                          status_code=200)
        send_delivery_status_to_service(notification.id)

    mock_data = {
        "id": str(notification.id),
        "reference": str(notification.client_reference),
        "to": notification.to,
        "status": notification.status,
        "created_at": datestr.strftime(DATETIME_FORMAT),  # the time GOV.UK email sent the request
        "completed_at": datestr.strftime(DATETIME_FORMAT),  # the last time the status was updated
        "sent_at": datestr.strftime(DATETIME_FORMAT),  # the time the email was sent
        "notification_type": notification_type
    }

    assert request_mock.call_count == 1
    assert request_mock.request_history[0].url == callback_api.url
    assert request_mock.request_history[0].method == 'POST'
    assert request_mock.request_history[0].text == json.dumps(mock_data)
    assert request_mock.request_history[0].headers["Content-type"] == "application/json"
    assert request_mock.request_history[0].headers["Authorization"] == "Bearer {}".format(callback_api.bearer_token)


@pytest.mark.parametrize("notification_type",
                         ["email", "letter", "sms"])
def test_send_delivery_status_to_service_does_not_sent_request_when_service_callback_api_does_not_exist(
        notify_db_session, mocker, notification_type):
    service = create_service(restricted=True)
    template = create_template(service=service, template_type=notification_type, subject='Hello')
    datestr = datetime(2017, 6, 20)

    notification = create_notification(template=template,
                                       created_at=datestr,
                                       updated_at=datestr,
                                       sent_at=datestr,
                                       status='sent'
                                       )
    mocked = mocker.patch("requests.request")
    send_delivery_status_to_service(notification.id)

    assert mocked.call_count == 0


@pytest.mark.parametrize("notification_type",
                         ["email", "letter", "sms"])
def test_send_delivery_status_to_service_retries_if_request_returns_500(notify_db_session,
                                                                        mocker,
                                                                        notification_type):
    callback_api, template = _set_up_test_data(notification_type)
    datestr = datetime(2017, 6, 20)
    notification = create_notification(template=template,
                                       created_at=datestr,
                                       updated_at=datestr,
                                       sent_at=datestr,
                                       status='sent'
                                       )
    mocked = mocker.patch('app.celery.service_callback_tasks.send_delivery_status_to_service.retry')
    with requests_mock.Mocker() as request_mock:
        request_mock.post(callback_api.url,
                          json={},
                          status_code=500)
        send_delivery_status_to_service(notification.id)

    assert mocked.call_count == 1
    assert mocked.call_args[1]['queue'] == 'retry-tasks'


@pytest.mark.parametrize("notification_type",
                         ["email", "letter", "sms"])
def test_send_delivery_status_to_service_retries_if_request_throws_unknown(notify_db_session,
                                                                           mocker,
                                                                           notification_type):

    callback_api, template = _set_up_test_data(notification_type)
    datestr = datetime(2017, 6, 20)
    notification = create_notification(template=template,
                                       created_at=datestr,
                                       updated_at=datestr,
                                       sent_at=datestr,
                                       status='sent'
                                       )

    mocked = mocker.patch('app.celery.service_callback_tasks.send_delivery_status_to_service.retry')
    mocker.patch("app.celery.tasks.request", side_effect=RequestException())

    send_delivery_status_to_service(notification.id)

    assert mocked.call_count == 1
    assert mocked.call_args[1]['queue'] == 'retry-tasks'


@pytest.mark.parametrize("notification_type",
                         ["email", "letter", "sms"])
def test_send_delivery_status_to_service_does_not_retries_if_request_returns_404(
        notify_db_session,
        mocker,
        notification_type
):
    callback_api, template = _set_up_test_data(notification_type)
    datestr = datetime(2017, 6, 20)
    notification = create_notification(template=template,
                                       created_at=datestr,
                                       updated_at=datestr,
                                       sent_at=datestr,
                                       status='sent'
                                       )
    mocked = mocker.patch('app.celery.service_callback_tasks.send_delivery_status_to_service.retry')
    with requests_mock.Mocker() as request_mock:
        request_mock.post(callback_api.url,
                          json={},
                          status_code=404)
        send_delivery_status_to_service(notification.id)

    assert mocked.call_count == 0


def test_send_delivery_status_to_service_retries_if_database_error(client, mocker):
    notification_id = uuid.uuid4()
    db_call = mocker.patch('app.celery.service_callback_tasks.get_notification_by_id', side_effect=SQLAlchemyError)
    retry = mocker.patch('app.celery.service_callback_tasks.send_delivery_status_to_service.retry')

    send_delivery_status_to_service(notification_id)

    db_call.assert_called_once_with(notification_id)
    retry.assert_called_once_with(queue=QueueNames.RETRY)
