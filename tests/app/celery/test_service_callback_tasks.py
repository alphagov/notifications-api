import uuid
import json
from datetime import datetime

from requests import RequestException
import pytest
import requests_mock
from sqlalchemy.exc import SQLAlchemyError

from app import (DATETIME_FORMAT)

from tests.app.conftest import (
    sample_service as create_sample_service,
    sample_template as create_sample_template,
)
from tests.app.db import (
    create_notification,
    create_user,
    create_service_callback_api
)
from app.celery.service_callback_tasks import send_delivery_status_to_service
from app.config import QueueNames


@pytest.mark.parametrize("notification_type",
                         ["email", "letter", "sms"])
def test_send_delivery_status_to_service_post_https_request_to_service(notify_db,
                                                                       notify_db_session,
                                                                       notification_type):
    user = create_user()
    service = create_sample_service(notify_db, notify_db_session, user=user, restricted=True)

    callback_api = create_service_callback_api(service=service, url="https://some.service.gov.uk/",
                                               bearer_token="something_unique")
    template = create_sample_template(
        notify_db, notify_db_session, service=service, template_type=notification_type, subject_line='Hello'
    )

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
        notify_db, notify_db_session, mocker, notification_type):
    service = create_sample_service(notify_db, notify_db_session, restricted=True)

    template = create_sample_template(
        notify_db, notify_db_session, service=service, template_type=notification_type, subject_line='Hello'
    )
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
def test_send_delivery_status_to_service_retries_if_request_returns_500(notify_db,
                                                                        notify_db_session,
                                                                        mocker,
                                                                        notification_type):
    user = create_user()
    service = create_sample_service(notify_db, notify_db_session, user=user, restricted=True)

    template = create_sample_template(
        notify_db, notify_db_session, service=service, template_type=notification_type, subject_line='Hello'
    )
    callback_api = create_service_callback_api(service=service, url="https://some.service.gov.uk/",
                                               bearer_token="something_unique")
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
def test_send_delivery_status_to_service_retries_if_request_throws_unknown(notify_db,
                                                                           notify_db_session,
                                                                           mocker,
                                                                           notification_type):
    user = create_user()
    service = create_sample_service(notify_db, notify_db_session, user=user, restricted=True)

    template = create_sample_template(
        notify_db, notify_db_session, service=service, template_type=notification_type, subject_line='Hello'
    )
    create_service_callback_api(service=service, url="https://some.service.gov.uk/",
                                bearer_token="something_unique")
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
def test_send_delivery_status_to_service_does_not_retries_if_request_returns_404(notify_db,
                                                                                 notify_db_session,
                                                                                 mocker,
                                                                                 notification_type):
    user = create_user()
    service = create_sample_service(notify_db, notify_db_session, user=user, restricted=True)

    template = create_sample_template(
        notify_db, notify_db_session, service=service, template_type=notification_type, subject_line='Hello'
    )
    callback_api = create_service_callback_api(service=service, url="https://some.service.gov.uk/",
                                               bearer_token="something_unique")
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
