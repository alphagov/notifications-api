import uuid
import pytest
from flask import current_app
from app.celery.tasks import (send_sms, send_sms_code, send_email_code, send_email, process_job)
from app import (firetext_client, aws_ses_client, encryption)
from app.clients.email.aws_ses import AwsSesClientException
from app.clients.sms.firetext import FiretextClientException
from app.dao import notifications_dao, jobs_dao
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm.exc import NoResultFound
from app.celery.tasks import s3
from app.celery import tasks
from tests.app import load_example_csv
from datetime import datetime
from freezegun import freeze_time


@freeze_time("2016-01-01 11:09:00.061258")
def test_should_process_sms_job(sample_job, mocker):
    mocker.patch('app.celery.tasks.s3.get_job_from_s3', return_value=load_example_csv('sms'))
    mocker.patch('app.celery.tasks.send_sms.apply_async')
    mocker.patch('app.encryption.encrypt', return_value="something_encrypted")
    mocker.patch('app.celery.tasks.create_uuid', return_value="uuid")

    process_job(sample_job.id)

    s3.get_job_from_s3.assert_called_once_with(sample_job.bucket_name, sample_job.id)
    tasks.send_sms.apply_async.assert_called_once_with(
        (str(sample_job.service_id),
         "uuid",
         "something_encrypted",
         "2016-01-01 11:09:00.061258"),
        queue="bulk-sms"
    )
    job = jobs_dao.dao_get_job_by_id(sample_job.id)
    assert job.status == 'finished'


def test_should_not_create_send_task_for_empty_file(sample_job, mocker):
    mocker.patch('app.celery.tasks.s3.get_job_from_s3', return_value=load_example_csv('empty'))
    mocker.patch('app.celery.tasks.send_sms.apply_async')

    process_job(sample_job.id)

    s3.get_job_from_s3.assert_called_once_with(sample_job.bucket_name, sample_job.id)
    job = jobs_dao.dao_get_job_by_id(sample_job.id)
    assert job.status == 'finished'
    tasks.send_sms.apply_async.assert_not_called


@freeze_time("2016-01-01 11:09:00.061258")
def test_should_process_email_job(sample_email_job, mocker):
    mocker.patch('app.celery.tasks.s3.get_job_from_s3', return_value=load_example_csv('email'))
    mocker.patch('app.celery.tasks.send_email.apply_async')
    mocker.patch('app.encryption.encrypt', return_value="something_encrypted")
    mocker.patch('app.celery.tasks.create_uuid', return_value="uuid")

    process_job(sample_email_job.id)

    s3.get_job_from_s3.assert_called_once_with(sample_email_job.bucket_name, sample_email_job.id)
    tasks.send_email.apply_async.assert_called_once_with(
        (str(sample_email_job.service_id),
         "uuid",
         sample_email_job.template.subject,
         "{}@{}".format(sample_email_job.service.email_from, "test.notify.com"),
         "something_encrypted",
         "2016-01-01 11:09:00.061258"),
        queue="bulk-email"
    )
    job = jobs_dao.dao_get_job_by_id(sample_email_job.id)
    assert job.status == 'finished'


def test_should_process_all_sms_job(sample_job, mocker):
    mocker.patch('app.celery.tasks.s3.get_job_from_s3', return_value=load_example_csv('multiple_sms'))
    mocker.patch('app.celery.tasks.send_sms.apply_async')
    mocker.patch('app.encryption.encrypt', return_value="something_encrypted")
    mocker.patch('app.celery.tasks.create_uuid', return_value="uuid")

    process_job(sample_job.id)

    s3.get_job_from_s3.assert_called_once_with(sample_job.bucket_name, sample_job.id)
    tasks.send_sms.apply_async.call_count == 10
    job = jobs_dao.dao_get_job_by_id(sample_job.id)
    assert job.status == 'finished'


def test_should_send_template_to_correct_sms_provider_and_persist(sample_template, mocker):
    notification = {
        "template": sample_template.id,
        "to": "+441234123123"
    }
    mocker.patch('app.encryption.decrypt', return_value=notification)
    mocker.patch('app.firetext_client.send_sms')
    mocker.patch('app.firetext_client.get_name', return_value="firetext")

    notification_id = uuid.uuid4()
    now = datetime.utcnow()
    send_sms(
        sample_template.service_id,
        notification_id,
        "encrypted-in-reality",
        now
    )

    firetext_client.send_sms.assert_called_once_with("+441234123123", sample_template.content)
    persisted_notification = notifications_dao.get_notification(sample_template.service_id, notification_id)
    assert persisted_notification.id == notification_id
    assert persisted_notification.to == '+441234123123'
    assert persisted_notification.template_id == sample_template.id
    assert persisted_notification.status == 'sent'
    assert persisted_notification.created_at == now
    assert persisted_notification.sent_at > now
    assert persisted_notification.sent_by == 'firetext'
    assert not persisted_notification.job_id


def test_should_send_template_to_correct_sms_provider_and_persist_with_job_id(sample_job, mocker):
    notification = {
        "template": sample_job.template.id,
        "job": sample_job.id,
        "to": "+441234123123"
    }
    mocker.patch('app.encryption.decrypt', return_value=notification)
    mocker.patch('app.firetext_client.send_sms')
    mocker.patch('app.firetext_client.get_name', return_value="firetext")

    notification_id = uuid.uuid4()
    now = datetime.utcnow()
    send_sms(
        sample_job.service.id,
        notification_id,
        "encrypted-in-reality",
        now)

    firetext_client.send_sms.assert_called_once_with("+441234123123", sample_job.template.content)
    persisted_notification = notifications_dao.get_notification(sample_job.template.service_id, notification_id)
    assert persisted_notification.id == notification_id
    assert persisted_notification.to == '+441234123123'
    assert persisted_notification.job_id == sample_job.id
    assert persisted_notification.template_id == sample_job.template.id
    assert persisted_notification.status == 'sent'
    assert persisted_notification.sent_at > now
    assert persisted_notification.created_at == now
    assert persisted_notification.sent_by == 'firetext'


def test_should_use_email_template_and_persist(sample_email_template, mocker):
    notification = {
        "template": sample_email_template.id,
        "to": "my_email@my_email.com"
    }
    mocker.patch('app.encryption.decrypt', return_value=notification)
    mocker.patch('app.aws_ses_client.send_email')
    mocker.patch('app.aws_ses_client.get_name', return_value='ses')

    notification_id = uuid.uuid4()
    now = datetime.utcnow()
    send_email(
        sample_email_template.service_id,
        notification_id,
        'subject',
        'email_from',
        "encrypted-in-reality",
        now)

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
    assert persisted_notification.created_at == now
    assert persisted_notification.sent_at > now
    assert persisted_notification.status == 'sent'
    assert persisted_notification.sent_by == 'ses'


def test_should_persist_notification_as_failed_if_sms_client_fails(sample_template, mocker):
    notification = {
        "template": sample_template.id,
        "to": "+441234123123"
    }
    mocker.patch('app.encryption.decrypt', return_value=notification)
    mocker.patch('app.firetext_client.send_sms', side_effect=FiretextClientException())
    mocker.patch('app.firetext_client.get_name', return_value="firetext")
    now = datetime.utcnow()

    notification_id = uuid.uuid4()

    send_sms(
        sample_template.service_id,
        notification_id,
        "encrypted-in-reality",
        now)

    firetext_client.send_sms.assert_called_once_with("+441234123123", sample_template.content)
    persisted_notification = notifications_dao.get_notification(sample_template.service_id, notification_id)
    assert persisted_notification.id == notification_id
    assert persisted_notification.to == '+441234123123'
    assert persisted_notification.template_id == sample_template.id
    assert persisted_notification.status == 'failed'
    assert persisted_notification.created_at == now
    assert persisted_notification.sent_at > now
    assert persisted_notification.sent_by == 'firetext'


def test_should_persist_notification_as_failed_if_email_client_fails(sample_email_template, mocker):
    notification = {
        "template": sample_email_template.id,
        "to": "my_email@my_email.com"
    }
    mocker.patch('app.encryption.decrypt', return_value=notification)
    mocker.patch('app.aws_ses_client.send_email', side_effect=AwsSesClientException())
    mocker.patch('app.aws_ses_client.get_name', return_value="ses")

    now = datetime.utcnow()

    notification_id = uuid.uuid4()

    send_email(
        sample_email_template.service_id,
        notification_id,
        'subject',
        'email_from',
        "encrypted-in-reality",
        now)

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
    assert persisted_notification.created_at == now
    assert persisted_notification.sent_by == 'ses'
    assert persisted_notification.sent_at > now


def test_should_not_send_sms_if_db_peristance_failed(sample_template, mocker):
    notification = {
        "template": sample_template.id,
        "to": "+441234123123"
    }
    mocker.patch('app.encryption.decrypt', return_value=notification)
    mocker.patch('app.firetext_client.send_sms')
    mocker.patch('app.db.session.add', side_effect=SQLAlchemyError())
    now = datetime.utcnow()

    notification_id = uuid.uuid4()

    send_sms(
        sample_template.service_id,
        notification_id,
        "encrypted-in-reality",
        now)

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
    now = datetime.utcnow()

    notification_id = uuid.uuid4()

    send_email(
        sample_email_template.service_id,
        notification_id,
        'subject',
        'email_from',
        "encrypted-in-reality",
        now)

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

    aws_ses_client.send_email.assert_called_once_with(
        current_app.config['VERIFY_CODE_FROM_EMAIL_ADDRESS'],
        verification['to'],
        "Verification code",
        verification['secret_code']
    )
