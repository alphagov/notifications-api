import uuid
import pytest
from flask import current_app
from app.celery.tasks import (send_sms, send_sms_code, send_email_code, send_email)
from app import (firetext_client, aws_ses_client, encryption)
from app.clients.email.aws_ses import AwsSesClientException
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
    assert not persisted_notification.job_id


def test_should_send_template_to_correct_sms_provider_and_persist_with_job_id(sample_job, mocker):
    notification = {
        "template": sample_job.template.id,
        "job": sample_job.id,
        "to": "+441234123123"
    }
    mocker.patch('app.encryption.decrypt', return_value=notification)
    mocker.patch('app.firetext_client.send_sms')

    notification_id = uuid.uuid4()

    send_sms(
        sample_job.service.id,
        notification_id,
        "encrypted-in-reality")

    firetext_client.send_sms.assert_called_once_with("+441234123123", sample_job.template.content)
    persisted_notification = notifications_dao.get_notification(sample_job.template.service_id, notification_id)
    assert persisted_notification.id == notification_id
    assert persisted_notification.to == '+441234123123'
    assert persisted_notification.job_id == sample_job.id
    assert persisted_notification.template_id == sample_job.template.id
    assert persisted_notification.status == 'sent'


def test_should_send_template_to_email_provider_and_persist(sample_email_template, mocker):
    notification = {
        "template": sample_email_template.id,
        "to": "my_email@my_email.com"
    }
    mocker.patch('app.encryption.decrypt', return_value=notification)
    mocker.patch('app.aws_ses_client.send_email')

    notification_id = uuid.uuid4()

    send_email(
        sample_email_template.service_id,
        notification_id,
        'subject',
        'email_from',
        "encrypted-in-reality")

    aws_ses_client.send_email.assert_called_once_with(
        "email_from",
        "my_email@my_email.com",
        "subject",
        sample_email_template.content
    )
    persisted_notification = notifications_dao.get_notification(sample_email_template.service_id, notification_id)
    assert persisted_notification.id == notification_id
    assert persisted_notification.to == 'my_email@my_email.com'
    assert persisted_notification.template_id == sample_email_template.id
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


def test_should_persist_notification_as_failed_if_email_client_fails(sample_email_template, mocker):
    notification = {
        "template": sample_email_template.id,
        "to": "my_email@my_email.com"
    }
    mocker.patch('app.encryption.decrypt', return_value=notification)
    mocker.patch('app.aws_ses_client.send_email', side_effect=AwsSesClientException())

    notification_id = uuid.uuid4()

    send_email(
        sample_email_template.service_id,
        notification_id,
        'subject',
        'email_from',
        "encrypted-in-reality")

    aws_ses_client.send_email.assert_called_once_with(
        "email_from",
        "my_email@my_email.com",
        "subject",
        sample_email_template.content
    )
    persisted_notification = notifications_dao.get_notification(sample_email_template.service_id, notification_id)
    assert persisted_notification.id == notification_id
    assert persisted_notification.to == 'my_email@my_email.com'
    assert persisted_notification.template_id == sample_email_template.id
    assert persisted_notification.status == 'failed'


def test_should_not_send_sms_if_db_peristance_failed(sample_template, mocker):
    notification = {
        "template": sample_template.id,
        "to": "+441234123123"
    }
    mocker.patch('app.encryption.decrypt', return_value=notification)
    mocker.patch('app.firetext_client.send_sms')
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


def test_should_not_send_email_if_db_peristance_failed(sample_email_template, mocker):
    notification = {
        "template": sample_email_template.id,
        "to": "my_email@my_email.com"
    }
    mocker.patch('app.encryption.decrypt', return_value=notification)
    mocker.patch('app.aws_ses_client.send_email')
    mocker.patch('app.db.session.add', side_effect=SQLAlchemyError())

    notification_id = uuid.uuid4()

    send_email(
        sample_email_template.service_id,
        notification_id,
        'subject',
        'email_from',
        "encrypted-in-reality")

    aws_ses_client.send_email.assert_not_called()
    with pytest.raises(NoResultFound) as e:
        notifications_dao.get_notification(sample_email_template.service_id, notification_id)
    assert 'No row was found for one' in str(e.value)


def test_should_send_sms_code(mocker):
    notification = {'to': '+441234123123',
                    'secret_code': '12345'}

    encrypted_notification = encryption.encrypt(notification)

    mocker.patch('app.firetext_client.send_sms')
    send_sms_code(encrypted_notification)
    firetext_client.send_sms.assert_called_once_with(notification['to'], notification['secret_code'])


def test_should_throw_firetext_client_exception(mocker):
    notification = {'to': '+441234123123',
                    'secret_code': '12345'}

    encrypted_notification = encryption.encrypt(notification)
    mocker.patch('app.firetext_client.send_sms', side_effect=FiretextClientException)
    send_sms_code(encrypted_notification)
    firetext_client.send_sms.assert_called_once_with(notification['to'], notification['secret_code'])


def test_should_send_email_code(mocker):
    verification = {'to': 'someone@it.gov.uk',
                    'secret_code': 11111}

    encrypted_verification = encryption.encrypt(verification)
    mocker.patch('app.aws_ses_client.send_email')

    send_email_code(encrypted_verification)

    aws_ses_client.send_email.assert_called_once_with(current_app.config['VERIFY_CODE_FROM_EMAIL_ADDRESS'],
                                                      verification['to'],
                                                      "Verification code",
                                                      verification['secret_code'])
