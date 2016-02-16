import uuid
from app.celery.tasks import send_sms
from app import twilio_client
from app.clients.sms.twilio import TwilioClientException
from app.dao import notifications_dao


def test_should_send_template_to_correct_sms_provider_and_persist(sample_template, mocker):
    notification = {
        "template": sample_template.id,
        "to": "+441234123123"
    }
    mocker.patch('app.encryption.decrypt', return_value=notification)
    mocker.patch('app.twilio_client.send_sms')

    notification_id = uuid.uuid4()

    send_sms(
        sample_template.service_id,
        notification_id,
        "encrypted-in-reality")

    twilio_client.send_sms.assert_called_once_with("+441234123123", sample_template.content)
    persisted_notification = notifications_dao.get_notification(sample_template.service_id, notification_id)
    assert persisted_notification.id == notification_id
    assert persisted_notification.to == '+441234123123'
    assert persisted_notification.template_id == sample_template.id
    assert persisted_notification.status == 'sent'


def test_should_persist_notification_as_failed_if_sms_client_fails(sample_template, mocker):
    notification = {
        "template": sample_template.id,
        "to": "+441234123123"
    }
    mocker.patch('app.encryption.decrypt', return_value=notification)
    mocker.patch('app.twilio_client.send_sms', side_effect=TwilioClientException())

    notification_id = uuid.uuid4()

    send_sms(
        sample_template.service_id,
        notification_id,
        "encrypted-in-reality")

    twilio_client.send_sms.assert_called_once_with("+441234123123", sample_template.content)
    persisted_notification = notifications_dao.get_notification(sample_template.service_id, notification_id)
    assert persisted_notification.id == notification_id
    assert persisted_notification.to == '+441234123123'
    assert persisted_notification.template_id == sample_template.id
    assert persisted_notification.status == 'failed'


def test_should_not_send_sms_if_db_peristance_failed(sample_template, mocker):
    notification = {
        "template": sample_template.id,
        "to": "+441234123123"
    }
    mocker.patch('app.encryption.decrypt', return_value=notification)
    mocker.patch('app.twilio_client.send_sms', side_effect=TwilioClientException())

    notification_id = uuid.uuid4()

    send_sms(
        sample_template.service_id,
        notification_id,
        "encrypted-in-reality")

    twilio_client.send_sms.assert_called_once_with("+441234123123", sample_template.content)
    persisted_notification = notifications_dao.get_notification(sample_template.service_id, notification_id)
    assert persisted_notification.id == notification_id
    assert persisted_notification.to == '+441234123123'
    assert persisted_notification.template_id == sample_template.id
    assert persisted_notification.status == 'failed'
