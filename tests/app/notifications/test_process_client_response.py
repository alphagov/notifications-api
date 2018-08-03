import uuid

import pytest

from app.clients import ClientException
from app.notifications.process_client_response import (
    validate_callback_data,
    process_sms_client_response
)
from app.celery.service_callback_tasks import create_delivery_status_callback_data
from tests.app.db import create_service_callback_api


def test_validate_callback_data_returns_none_when_valid():
    form = {'status': 'good',
            'reference': 'send-sms-code'}
    fields = ['status', 'reference']
    client_name = 'sms client'

    assert validate_callback_data(form, fields, client_name) is None


def test_validate_callback_data_return_errors_when_fields_are_empty():
    form = {'monkey': 'good'}
    fields = ['status', 'cid']
    client_name = 'sms client'

    errors = validate_callback_data(form, fields, client_name)
    assert len(errors) == 2
    assert "{} callback failed: {} missing".format(client_name, 'status') in errors
    assert "{} callback failed: {} missing".format(client_name, 'cid') in errors


def test_validate_callback_data_can_handle_integers():
    form = {'status': 00, 'cid': 'fsdfadfsdfas'}
    fields = ['status', 'cid']
    client_name = 'sms client'

    result = validate_callback_data(form, fields, client_name)
    assert result is None


def test_validate_callback_data_returns_error_for_empty_string():
    form = {'status': '', 'cid': 'fsdfadfsdfas'}
    fields = ['status', 'cid']
    client_name = 'sms client'

    result = validate_callback_data(form, fields, client_name)
    assert result is not None
    assert "{} callback failed: {} missing".format(client_name, 'status') in result


def test_outcome_statistics_called_for_successful_callback(sample_notification, mocker):
    mocker.patch(
        'app.notifications.process_client_response.notifications_dao.update_notification_status_by_id',
        return_value=sample_notification
    )
    send_mock = mocker.patch(
        'app.celery.service_callback_tasks.send_delivery_status_to_service.apply_async'
    )
    callback_api = create_service_callback_api(service=sample_notification.service, url="https://original_url.com")
    reference = str(uuid.uuid4())

    success, error = process_sms_client_response(status='3', provider_reference=reference, client_name='MMG')
    assert success == "MMG callback succeeded. reference {} updated".format(str(reference))
    assert error is None
    encrypted_data = create_delivery_status_callback_data(sample_notification, callback_api)
    send_mock.assert_called_once_with([str(sample_notification.id), encrypted_data],
                                      queue="service-callbacks")


def test_sms_resonse_does_not_call_send_callback_if_no_db_entry(sample_notification, mocker):
    mocker.patch(
        'app.notifications.process_client_response.notifications_dao.update_notification_status_by_id',
        return_value=sample_notification
    )
    send_mock = mocker.patch(
        'app.celery.service_callback_tasks.send_delivery_status_to_service.apply_async'
    )
    reference = str(uuid.uuid4())
    process_sms_client_response(status='3', provider_reference=reference, client_name='MMG')
    send_mock.assert_not_called()


def test_process_sms_response_return_success_for_send_sms_code_reference(mocker):
    success, error = process_sms_client_response(
        status='000', provider_reference='send-sms-code', client_name='sms-client')
    assert success == "{} callback succeeded: send-sms-code".format('sms-client')
    assert error is None


def test_process_sms_updates_sent_by_with_client_name_if_not_in_noti(notify_db, sample_notification):
    sample_notification.sent_by = None
    success, error = process_sms_client_response(
        status='3', provider_reference=str(sample_notification.id), client_name='MMG')
    assert error is None
    assert success == 'MMG callback succeeded. reference {} updated'.format(sample_notification.id)
    assert sample_notification.sent_by == 'mmg'


def test_process_sms_does_not_update_sent_by_if_already_set(mocker, notify_db, sample_notification):
    mock_update = mocker.patch('app.notifications.process_client_response.set_notification_sent_by')
    sample_notification.sent_by = 'MMG'
    process_sms_client_response(
        status='3', provider_reference=str(sample_notification.id), client_name='MMG')
    assert not mock_update.called


def test_process_sms_response_returns_error_bad_reference(mocker):
    success, error = process_sms_client_response(
        status='000', provider_reference='something-bad', client_name='sms-client')
    assert success is None
    assert error == "{} callback with invalid reference {}".format('sms-client', 'something-bad')


def test_process_sms_response_raises_client_exception_for_unknown_sms_client(mocker):
    success, error = process_sms_client_response(
        status='000', provider_reference=str(uuid.uuid4()), client_name='sms-client')

    assert success is None
    assert error == 'unknown sms client: {}'.format('sms-client')


def test_process_sms_response_raises_client_exception_for_unknown_status(mocker):
    with pytest.raises(ClientException) as e:
        process_sms_client_response(status='000', provider_reference=str(uuid.uuid4()), client_name='Firetext')

    assert "{} callback failed: status {} not found.".format('Firetext', '000') in str(e.value)
