import uuid
from datetime import datetime

import pytest
from freezegun import freeze_time

from app import statsd_client
from app.clients import ClientException
from app.celery.process_sms_client_response_tasks import process_sms_client_response
from app.celery.service_callback_tasks import create_delivery_status_callback_data
from app.models import NOTIFICATION_TECHNICAL_FAILURE
from tests.app.db import create_service_callback_api


def test_process_sms_client_response_raises_error_if_reference_is_not_a_valid_uuid(client):
    with pytest.raises(ValueError):
        process_sms_client_response(
            status='000', provider_reference='something-bad', client_name='sms-client')


@pytest.mark.parametrize('client_name', ('Firetext', 'MMG'))
def test_process_sms_response_raises_client_exception_for_unknown_status(
    sample_notification,
    mocker,
    client_name,
):
    with pytest.raises(ClientException) as e:
        process_sms_client_response(
            status='000',
            provider_reference=str(sample_notification.id),
            client_name=client_name,
        )

    assert f"{client_name} callback failed: status {'000'} not found." in str(e.value)
    assert sample_notification.status == NOTIFICATION_TECHNICAL_FAILURE


@pytest.mark.parametrize('status, sms_provider, expected_notification_status', [
    ('0', 'Firetext', 'delivered'),
    ('1', 'Firetext', 'permanent-failure'),
    ('2', 'Firetext', 'pending'),
    ('2', 'MMG', 'permanent-failure'),
    ('3', 'MMG', 'delivered'),
    ('4', 'MMG', 'temporary-failure'),
    ('5', 'MMG', 'permanent-failure'),
])
def test_process_sms_client_response_updates_notification_status(
    sample_notification,
    mocker,
    status,
    sms_provider,
    expected_notification_status,
):
    sample_notification.status = 'sending'
    process_sms_client_response(status, str(sample_notification.id), sms_provider)

    assert sample_notification.status == expected_notification_status


@pytest.mark.parametrize('code, expected_notification_status, reason', [
    ('101', 'permanent-failure', 'Unknown Subscriber'),
    ('102', 'temporary-failure', 'Absent Subscriber'),
    (None, 'temporary-failure', None),
    ('000', 'temporary-failure', None)
])
def test_process_sms_client_response_updates_notification_status_when_called_second_time(
    sample_notification,
    mocker,
    code,
    expected_notification_status,
    reason
):
    mock_logger = mocker.patch('app.celery.tasks.current_app.logger.info')
    sample_notification.status = 'sending'
    process_sms_client_response('2', str(sample_notification.id), 'Firetext')

    process_sms_client_response('1', str(sample_notification.id), 'Firetext', code)

    if code and code != '000':
        message = f'Updating notification id {sample_notification.id} to status {expected_notification_status}, reason: {reason}'  # noqa
        mock_logger.assert_called_with(message)

    assert sample_notification.status == expected_notification_status


def test_process_sms_client_response_updates_notification_status_when_code_unknown(
    sample_notification,
    mocker,
):
    mock_logger = mocker.patch('app.celery.tasks.current_app.logger.warning')
    sample_notification.status = 'sending'
    process_sms_client_response('2', str(sample_notification.id), 'Firetext')

    process_sms_client_response('1', str(sample_notification.id), 'Firetext', '789')

    mock_logger.assert_called_once_with('Failure code 789 from Firetext not recognised')
    assert sample_notification.status == 'temporary-failure'


def test_sms_response_does_not_send_callback_if_notification_is_not_in_the_db(sample_service, mocker):
    mocker.patch(
        'app.celery.process_sms_client_response_tasks.get_service_delivery_status_callback_api_for_service',
        return_value='mock-delivery-callback-for-service')
    send_mock = mocker.patch(
        'app.celery.service_callback_tasks.send_delivery_status_to_service.apply_async'
    )
    reference = str(uuid.uuid4())
    process_sms_client_response(status='3', provider_reference=reference, client_name='MMG')
    send_mock.assert_not_called()


@freeze_time('2001-01-01T12:00:00')
def test_process_sms_client_response_records_statsd_metrics(sample_notification, client, mocker):
    mocker.patch('app.statsd_client.incr')
    mocker.patch('app.statsd_client.timing_with_dates')

    sample_notification.status = 'sending'
    sample_notification.sent_at = datetime.utcnow()

    process_sms_client_response('0', str(sample_notification.id), 'Firetext')

    statsd_client.incr.assert_any_call("callback.firetext.delivered")
    statsd_client.timing_with_dates.assert_any_call(
        "callback.firetext.elapsed-time", datetime.utcnow(), sample_notification.sent_at
    )


def test_process_sms_updates_billable_units_if_zero(sample_notification):
    sample_notification.billable_units = 0
    process_sms_client_response('3', str(sample_notification.id), 'MMG')

    assert sample_notification.billable_units == 1


def test_process_sms_response_does_not_send_service_callback_for_pending_notifications(sample_notification, mocker):
    mocker.patch(
        'app.celery.process_sms_client_response_tasks.get_service_delivery_status_callback_api_for_service',
        return_value='fake-callback')
    send_mock = mocker.patch('app.celery.service_callback_tasks.send_delivery_status_to_service.apply_async')
    process_sms_client_response('2', str(sample_notification.id), 'Firetext')
    send_mock.assert_not_called()


def test_outcome_statistics_called_for_successful_callback(sample_notification, mocker):
    send_mock = mocker.patch(
        'app.celery.service_callback_tasks.send_delivery_status_to_service.apply_async'
    )
    callback_api = create_service_callback_api(service=sample_notification.service, url="https://original_url.com")
    reference = str(sample_notification.id)

    process_sms_client_response('3', reference, 'MMG')

    encrypted_data = create_delivery_status_callback_data(sample_notification, callback_api)
    send_mock.assert_called_once_with([reference, encrypted_data],
                                      queue="service-callbacks")


def test_process_sms_updates_sent_by_with_client_name_if_not_in_noti(sample_notification):
    sample_notification.sent_by = None
    process_sms_client_response('3', str(sample_notification.id), 'MMG')

    assert sample_notification.sent_by == 'mmg'
