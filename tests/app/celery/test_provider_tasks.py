from celery.exceptions import MaxRetriesExceededError
from app.celery import provider_tasks
from app.celery.provider_tasks import send_sms_to_provider, send_email_to_provider
from app.clients.email import EmailClientException
from app.models import Notification
from tests.app.conftest import sample_notification


def test_should_have_decorated_tasks_functions():
    assert send_sms_to_provider.__wrapped__.__name__ == 'send_sms_to_provider'
    assert send_email_to_provider.__wrapped__.__name__ == 'send_email_to_provider'


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


def test_should_go_into_technical_error_if_exceeds_retries(
        notify_db,
        notify_db_session,
        sample_service,
        mocker):

    notification = sample_notification(notify_db=notify_db, notify_db_session=notify_db_session,
                                       service=sample_service, status='created')

    mocker.patch('app.delivery.send_to_providers.send_sms_to_provider', side_effect=Exception("EXPECTED"))
    mocker.patch('app.celery.provider_tasks.send_sms_to_provider.retry', side_effect=MaxRetriesExceededError())

    send_sms_to_provider(
        notification.service_id,
        notification.id
    )

    provider_tasks.send_sms_to_provider.retry.assert_called_with(queue='retry', countdown=10)

    db_notification = Notification.query.filter_by(id=notification.id).one()
    assert db_notification.status == 'technical-failure'


def test_send_email_to_provider_should_go_into_technical_error_if_exceeds_retries(
        notify_db,
        notify_db_session,
        sample_service,
        sample_email_template,
        mocker):

    notification = sample_notification(notify_db=notify_db, notify_db_session=notify_db_session,
                                       service=sample_service, status='created', template=sample_email_template)

    mocker.patch('app.aws_ses_client.send_email', side_effect=EmailClientException("EXPECTED"))
    mocker.patch('app.celery.provider_tasks.send_email_to_provider.retry', side_effect=MaxRetriesExceededError())

    send_email_to_provider(
        notification.service_id,
        notification.id
    )

    provider_tasks.send_email_to_provider.retry.assert_called_with(queue='retry', countdown=10)

    db_notification = Notification.query.filter_by(id=notification.id).one()
    assert db_notification.status == 'technical-failure'
