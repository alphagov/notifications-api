import uuid
import pytest
from app.celery.tasks import (send_sms, send_sms_code)
from app import twilio_client, encryption
from app.clients.sms.twilio import TwilioClientException
from app.celery.tasks import send_sms
from app import firetext_client
from app.clients.sms.firetext import FiretextClientException
from app.dao import notifications_dao
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm.exc import NoResultFound


def test_should_send_template_to_correct_sms_provider_and_persist(sample_template, mocker):
    notification = {
        "template": sample_template.id,
        "to": "+441234123123"
    }
    mocker.patch('app.encryption.decrypt', return_value=notification)
    mocker.patch('app.firetext_client.send_sms')

    notification_id = uuid.uuid4()

    send_sms(
        sample_template.service_id,
        notification_id,
        "encrypted-in-reality")

    firetext_client.send_sms.assert_called_once_with("+441234123123", sample_template.content)
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
    mocker.patch('app.firetext_client.send_sms', side_effect=FiretextClientException())

    notification_id = uuid.uuid4()

    send_sms(
        sample_template.service_id,
        notification_id,
        "encrypted-in-reality")

    firetext_client.send_sms.assert_called_once_with("+441234123123", sample_template.content)
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
    mocker.patch('app.firetext_client.send_sms', side_effect=FiretextClientException())
    mocker.patch('app.db.session.add', side_effect=SQLAlchemyError())

    notification_id = uuid.uuid4()

    send_sms(
        sample_template.service_id,
        notification_id,
        "encrypted-in-reality")

    firetext_client.send_sms.assert_not_called()
    with pytest.raises(NoResultFound) as e:
        notifications_dao.get_notification(sample_template.service_id, notification_id)
    assert 'No row was found for one' in str(e.value)


def test_should_send_sms_code(mocker):
    notification = {'to': '+441234123123',
                    'secret_code': '12345'}

    encrypted_notification = encryption.encrypt(notification)

    mocker.patch('app.twilio_client.send_sms')
    send_sms_code(encrypted_notification)
    twilio_client.send_sms.assert_called_once_with(notification['to'], notification['secret_code'])


def test_should_throw_twilio_exception(mocker):
    notification = {'to': '+441234123123',
                    'secret_code': '12345'}

    encrypted_notification = encryption.encrypt(notification)
    mocker.patch('app.twilio_client.send_sms', side_effect=TwilioClientException)
    send_sms_code(encrypted_notification)
    twilio_client.send_sms.assert_called_once_with(notification['to'], notification['secret_code'])
