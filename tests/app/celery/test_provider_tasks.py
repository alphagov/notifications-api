from celery.exceptions import MaxRetriesExceededError
from notifications_utils.recipients import InvalidEmailError

import app
from app.celery import provider_tasks
from app.celery.provider_tasks import deliver_sms, deliver_email


def test_should_have_decorated_tasks_functions():
    assert deliver_sms.__wrapped__.__name__ == 'deliver_sms'
    assert deliver_email.__wrapped__.__name__ == 'deliver_email'


def test_should_by_10_second_delay_as_default():
    assert provider_tasks.retry_iteration_to_delay() == 10


def test_should_by_10_second_delay_on_unmapped_retry_iteration():
    assert provider_tasks.retry_iteration_to_delay(99) == 10


def test_should_by_10_second_delay_on_retry_one():
    assert provider_tasks.retry_iteration_to_delay(0) == 10


def test_should_by_1_minute_delay_on_retry_two():
    assert provider_tasks.retry_iteration_to_delay(1) == 60


def test_should_by_5_minute_delay_on_retry_two():
    assert provider_tasks.retry_iteration_to_delay(2) == 300


def test_should_by_60_minute_delay_on_retry_two():
    assert provider_tasks.retry_iteration_to_delay(3) == 3600


def test_should_by_240_minute_delay_on_retry_two():
    assert provider_tasks.retry_iteration_to_delay(4) == 14400


def test_should_call_send_sms_to_provider_from_deliver_sms_task(
        notify_db,
        notify_db_session,
        sample_notification,
        mocker):
    mocker.patch('app.delivery.send_to_providers.send_sms_to_provider')

    deliver_sms(sample_notification.id)
    app.delivery.send_to_providers.send_sms_to_provider.assert_called_with(sample_notification)


def test_should_add_to_retry_queue_if_notification_not_found_in_deliver_sms_task(
        notify_db,
        notify_db_session,
        mocker):
    mocker.patch('app.delivery.send_to_providers.send_sms_to_provider')
    mocker.patch('app.celery.provider_tasks.deliver_sms.retry')

    notification_id = app.create_uuid()

    deliver_sms(notification_id)
    app.delivery.send_to_providers.send_sms_to_provider.assert_not_called()
    app.celery.provider_tasks.deliver_sms.retry.assert_called_with(queue="retry", countdown=10)


def test_should_call_send_email_to_provider_from_deliver_email_task(
        notify_db,
        notify_db_session,
        sample_notification,
        mocker):
    mocker.patch('app.delivery.send_to_providers.send_email_to_provider')

    deliver_email(sample_notification.id)
    app.delivery.send_to_providers.send_email_to_provider.assert_called_with(sample_notification)


def test_should_add_to_retry_queue_if_notification_not_found_in_deliver_email_task(mocker):
    mocker.patch('app.delivery.send_to_providers.send_email_to_provider')
    mocker.patch('app.celery.provider_tasks.deliver_email.retry')

    notification_id = app.create_uuid()

    deliver_email(notification_id)
    app.delivery.send_to_providers.send_email_to_provider.assert_not_called()
    app.celery.provider_tasks.deliver_email.retry.assert_called_with(queue="retry", countdown=10)


# DO THESE FOR THE 4 TYPES OF TASK

def test_should_go_into_technical_error_if_exceeds_retries_on_deliver_sms_task(sample_notification, mocker):
    mocker.patch('app.delivery.send_to_providers.send_sms_to_provider', side_effect=Exception("EXPECTED"))
    mocker.patch('app.celery.provider_tasks.deliver_sms.retry', side_effect=MaxRetriesExceededError())

    deliver_sms(sample_notification.id)

    provider_tasks.deliver_sms.retry.assert_called_with(queue='retry', countdown=10)

    assert sample_notification.status == 'technical-failure'


def test_should_go_into_technical_error_if_exceeds_retries_on_deliver_email_task(sample_notification, mocker):
    mocker.patch('app.delivery.send_to_providers.send_email_to_provider', side_effect=Exception("EXPECTED"))
    mocker.patch('app.celery.provider_tasks.deliver_email.retry', side_effect=MaxRetriesExceededError())

    deliver_email(sample_notification.id)

    provider_tasks.deliver_email.retry.assert_called_with(queue='retry', countdown=10)
    assert sample_notification.status == 'technical-failure'


def test_should_technical_error_and_not_retry_if_invalid_email(sample_notification, mocker):
    mocker.patch('app.delivery.send_to_providers.send_email_to_provider', side_effect=InvalidEmailError('bad email'))
    mocker.patch('app.celery.provider_tasks.deliver_email.retry')

    deliver_email(sample_notification.id)

    assert provider_tasks.deliver_email.retry.called is False
    assert sample_notification.status == 'technical-failure'


def test_send_sms_should_switch_providers_on_provider_failure(sample_notification, mocker):
    provider_to_use = mocker.patch('app.delivery.send_to_providers.provider_to_use')
    provider_to_use.return_value.send_sms.side_effect = Exception('Error')
    switch_provider_mock = mocker.patch('app.delivery.send_to_providers.dao_toggle_sms_provider')
    mocker.patch('app.celery.provider_tasks.deliver_sms.retry')

    deliver_sms(sample_notification.id)

    assert switch_provider_mock.called is True


def test_send_sms_should_not_switch_providers_on_non_provider_failure(
    sample_notification,
    mocker
):
    mocker.patch(
        'app.delivery.send_to_providers.send_sms_to_provider',
        side_effect=Exception("Non Provider Exception")
    )
    switch_provider_mock = mocker.patch('app.delivery.send_to_providers.dao_toggle_sms_provider')
    mocker.patch('app.celery.provider_tasks.deliver_sms.retry')

    deliver_sms(sample_notification.id)

    assert switch_provider_mock.called is False
