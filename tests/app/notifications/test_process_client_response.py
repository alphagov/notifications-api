import uuid

from app.notifications.process_client_response import (
    validate_callback_data,
    process_sms_client_response
)


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
    stats_mock = mocker.patch('app.notifications.process_client_response.create_outcome_notification_statistic_tasks')
    mocker.patch(
        'app.notifications.process_client_response.notifications_dao.update_notification_status_by_id',
        return_value=sample_notification
    )

    reference = str(uuid.uuid4())

    success, error = process_sms_client_response(status='3', reference=reference, client_name='MMG')
    assert success == "MMG callback succeeded. reference {} updated".format(str(reference))
    assert error is None
    stats_mock.assert_called_once_with(sample_notification)


def test_process_sms_response_return_success_for_send_sms_code_reference(mocker):
    stats_mock = mocker.patch('app.notifications.process_client_response.create_outcome_notification_statistic_tasks')

    success, error = process_sms_client_response(status='000', reference='send-sms-code', client_name='sms-client')
    assert success == "{} callback succeeded: send-sms-code".format('sms-client')
    assert error is None
    stats_mock.assert_not_called()


def test_process_sms_response_returns_error_bad_reference(mocker):
    stats_mock = mocker.patch('app.notifications.process_client_response.create_outcome_notification_statistic_tasks')

    success, error = process_sms_client_response(status='000', reference='something-bad', client_name='sms-client')
    assert success is None
    assert error == "{} callback with invalid reference {}".format('sms-client', 'something-bad')
    stats_mock.assert_not_called()


def test_process_sms_response_returns_error_for_unknown_sms_client(mocker):
    stats_mock = mocker.patch('app.notifications.process_client_response.create_outcome_notification_statistic_tasks')
    success, error = process_sms_client_response(status='000', reference=str(uuid.uuid4()), client_name='sms-client')

    assert success is None
    assert error == 'unknown sms client: {}'.format('sms-client')
    stats_mock.assert_not_called()


def test_process_sms_response_returns_error_for_unknown_status(mocker):
    stats_mock = mocker.patch('app.notifications.process_client_response.create_outcome_notification_statistic_tasks')

    success, error = process_sms_client_response(status='000', reference=str(uuid.uuid4()), client_name='Firetext')
    assert success is None
    assert error == "{} callback failed: status {} not found.".format('Firetext', '000')
    stats_mock.assert_not_called()
