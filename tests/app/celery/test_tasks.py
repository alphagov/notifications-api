import uuid
import pytest
from flask import current_app
from utils.recipients import validate_phone_number, format_phone_number

from app.celery.tasks import (
    send_sms,
    send_sms_code,
    send_email_code,
    send_email,
    process_job,
    email_invited_user,
    email_reset_password,
    delete_verify_codes,
    delete_invitations,
    delete_failed_notifications,
    delete_successful_notifications
)
from app import (firetext_client, aws_ses_client, encryption, DATETIME_FORMAT)
from app.clients.email.aws_ses import AwsSesClientException
from app.clients.sms.firetext import FiretextClientException
from app.dao import notifications_dao, jobs_dao
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm.exc import NoResultFound
from app.celery.tasks import s3
from app.celery import tasks
from tests.app import load_example_csv
from datetime import datetime, timedelta
from freezegun import freeze_time
from tests.app.conftest import (
    sample_service,
    sample_user,
    sample_template,
    sample_job,
    sample_email_template,
    sample_notification
)


class AnyStringWith(str):
    def __eq__(self, other):
        return self in other


def firetext_error():
    return {'code': 0, 'description': 'error'}


def test_should_call_delete_successful_notifications_in_task(notify_api, mocker):
    mocker.patch('app.celery.tasks.delete_successful_notifications_created_more_than_a_day_ago')
    delete_successful_notifications()
    assert tasks.delete_successful_notifications_created_more_than_a_day_ago.call_count == 1


def test_should_call_delete_failed_notifications_in_task(notify_api, mocker):
    mocker.patch('app.celery.tasks.delete_failed_notifications_created_more_than_a_week_ago')
    delete_failed_notifications()
    assert tasks.delete_failed_notifications_created_more_than_a_week_ago.call_count == 1


def test_should_call_delete_codes_on_delete_verify_codes_task(notify_api, mocker):
    mocker.patch('app.celery.tasks.delete_codes_older_created_more_than_a_day_ago')
    delete_verify_codes()
    assert tasks.delete_codes_older_created_more_than_a_day_ago.call_count == 1


def test_should_call_delete_invotations_on_delete_invitations_task(notify_api, mocker):
    mocker.patch('app.celery.tasks.delete_invitations_created_more_than_two_days_ago')
    delete_invitations()
    assert tasks.delete_invitations_created_more_than_two_days_ago.call_count == 1


@freeze_time("2016-01-01 11:09:00.061258")
def test_should_process_sms_job(sample_job, mocker):
    mocker.patch('app.celery.tasks.s3.get_job_from_s3', return_value=load_example_csv('sms'))
    mocker.patch('app.celery.tasks.send_sms.apply_async')
    mocker.patch('app.encryption.encrypt', return_value="something_encrypted")
    mocker.patch('app.celery.tasks.create_uuid', return_value="uuid")

    process_job(sample_job.id)

    s3.get_job_from_s3.assert_called_once_with(sample_job.bucket_name, sample_job.id)
    assert encryption.encrypt.call_args[0][0]['to'] == '+441234123123'
    assert encryption.encrypt.call_args[0][0]['personalisation'] == {}
    tasks.send_sms.apply_async.assert_called_once_with(
        (str(sample_job.service_id),
         "uuid",
         "something_encrypted",
         "2016-01-01T11:09:00.061258"),
        queue="bulk-sms"
    )
    job = jobs_dao.dao_get_job_by_id(sample_job.id)
    assert job.status == 'finished'


@freeze_time("2016-01-01 11:09:00.061258")
def test_should_not_process_sms_job_if_would_exceed_send_limits(notify_db, notify_db_session, mocker):
    service = sample_service(notify_db, notify_db_session, limit=9)
    job = sample_job(notify_db, notify_db_session, service=service, notification_count=10)

    mocker.patch('app.celery.tasks.s3.get_job_from_s3', return_value=load_example_csv('multiple_sms'))
    mocker.patch('app.celery.tasks.send_sms.apply_async')
    mocker.patch('app.encryption.encrypt', return_value="something_encrypted")
    mocker.patch('app.celery.tasks.create_uuid', return_value="uuid")

    process_job(job.id)

    s3.get_job_from_s3.assert_not_called()
    job = jobs_dao.dao_get_job_by_id(job.id)
    assert job.status == 'sending limits exceeded'
    tasks.send_sms.apply_async.assert_not_called()


def test_should_not_process_sms_job_if_would_exceed_send_limits_inc_today(notify_db, notify_db_session, mocker):
    service = sample_service(notify_db, notify_db_session, limit=1)
    job = sample_job(notify_db, notify_db_session, service=service)

    sample_notification(notify_db, notify_db_session, service=service, job=job)

    mocker.patch('app.celery.tasks.s3.get_job_from_s3', return_value=load_example_csv('sms'))
    mocker.patch('app.celery.tasks.send_sms.apply_async')
    mocker.patch('app.encryption.encrypt', return_value="something_encrypted")
    mocker.patch('app.celery.tasks.create_uuid', return_value="uuid")

    process_job(job.id)

    job = jobs_dao.dao_get_job_by_id(job.id)
    assert job.status == 'sending limits exceeded'
    s3.get_job_from_s3.assert_not_called()
    tasks.send_sms.apply_async.assert_not_called()


def test_should_not_process_email_job_if_would_exceed_send_limits_inc_today(notify_db, notify_db_session, mocker):
    service = sample_service(notify_db, notify_db_session, limit=1)
    template = sample_email_template(notify_db, notify_db_session, service=service)
    job = sample_job(notify_db, notify_db_session, service=service, template=template)

    sample_notification(notify_db, notify_db_session, service=service, job=job)

    mocker.patch('app.celery.tasks.s3.get_job_from_s3', return_value=load_example_csv('email'))
    mocker.patch('app.celery.tasks.send_email.apply_async')
    mocker.patch('app.encryption.encrypt', return_value="something_encrypted")
    mocker.patch('app.celery.tasks.create_uuid', return_value="uuid")

    process_job(job.id)

    job = jobs_dao.dao_get_job_by_id(job.id)
    assert job.status == 'sending limits exceeded'
    s3.get_job_from_s3.assert_not_called()
    tasks.send_email.apply_async.assert_not_called()


@freeze_time("2016-01-01 11:09:00.061258")
def test_should_not_process_email_job_if_would_exceed_send_limits(notify_db, notify_db_session, mocker):
    service = sample_service(notify_db, notify_db_session, limit=0)
    template = sample_email_template(notify_db, notify_db_session, service=service)
    job = sample_job(notify_db, notify_db_session, service=service, template=template)

    mocker.patch('app.celery.tasks.s3.get_job_from_s3', return_value=load_example_csv('email'))
    mocker.patch('app.celery.tasks.send_email.apply_async')
    mocker.patch('app.encryption.encrypt', return_value="something_encrypted")
    mocker.patch('app.celery.tasks.create_uuid', return_value="uuid")

    process_job(job.id)

    s3.get_job_from_s3.assert_not_called
    job = jobs_dao.dao_get_job_by_id(job.id)
    assert job.status == 'sending limits exceeded'
    tasks.send_email.apply_async.assert_not_called


@freeze_time("2016-01-01 11:09:00.061258")
def test_should_process_sms_job_if_exactly_on_send_limits(notify_db, notify_db_session, mocker):
    service = sample_service(notify_db, notify_db_session, limit=10)
    template = sample_email_template(notify_db, notify_db_session, service=service)
    job = sample_job(notify_db, notify_db_session, service=service, template=template, notification_count=10)

    mocker.patch('app.celery.tasks.s3.get_job_from_s3', return_value=load_example_csv('multiple_email'))
    mocker.patch('app.celery.tasks.send_email.apply_async')
    mocker.patch('app.encryption.encrypt', return_value="something_encrypted")
    mocker.patch('app.celery.tasks.create_uuid', return_value="uuid")

    process_job(job.id)

    s3.get_job_from_s3.assert_called_once_with(job.bucket_name, job.id)
    job = jobs_dao.dao_get_job_by_id(job.id)
    assert job.status == 'finished'
    tasks.send_email.apply_async.assert_called_with(
        (str(job.service_id),
         "uuid",
         job.template.subject,
         "{}@{}".format(job.service.email_from, "test.notify.com"),
         "something_encrypted",
         "2016-01-01T11:09:00.061258"),
        queue="bulk-email"
    )


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
    assert encryption.encrypt.call_args[0][0]['to'] == 'test@test.com'
    assert encryption.encrypt.call_args[0][0]['personalisation'] == {}
    tasks.send_email.apply_async.assert_called_once_with(
        (str(sample_email_job.service_id),
         "uuid",
         sample_email_job.template.subject,
         "{}@{}".format(sample_email_job.service.email_from, "test.notify.com"),
         "something_encrypted",
         "2016-01-01T11:09:00.061258"),
        queue="bulk-email"
    )
    job = jobs_dao.dao_get_job_by_id(sample_email_job.id)
    assert job.status == 'finished'


def test_should_process_all_sms_job(sample_job, sample_job_with_placeholdered_template, mocker):
    mocker.patch('app.celery.tasks.s3.get_job_from_s3', return_value=load_example_csv('multiple_sms'))
    mocker.patch('app.celery.tasks.send_sms.apply_async')
    mocker.patch('app.encryption.encrypt', return_value="something_encrypted")
    mocker.patch('app.celery.tasks.create_uuid', return_value="uuid")

    process_job(sample_job_with_placeholdered_template.id)

    s3.get_job_from_s3.assert_called_once_with(
        sample_job_with_placeholdered_template.bucket_name,
        sample_job_with_placeholdered_template.id
    )
    assert encryption.encrypt.call_args[0][0]['to'] == '+441234123120'
    assert encryption.encrypt.call_args[0][0]['personalisation'] == {'name': 'chris'}
    tasks.send_sms.apply_async.call_count == 10
    job = jobs_dao.dao_get_job_by_id(sample_job_with_placeholdered_template.id)
    assert job.status == 'finished'


def test_should_send_template_to_correct_sms_provider_and_persist(sample_template_with_placeholders, mocker):
    notification = {
        "template": sample_template_with_placeholders.id,
        "to": "+447234123123",
        "personalisation": {"name": "Jo"}
    }
    mocker.patch('app.encryption.decrypt', return_value=notification)
    mocker.patch('app.firetext_client.send_sms')
    mocker.patch('app.firetext_client.get_name', return_value="firetext")

    notification_id = uuid.uuid4()
    now = datetime.utcnow()
    send_sms(
        sample_template_with_placeholders.service_id,
        notification_id,
        "encrypted-in-reality",
        now.strftime(DATETIME_FORMAT)
    )

    firetext_client.send_sms.assert_called_once_with(
        to=format_phone_number(validate_phone_number("+447234123123")),
        content="Sample service: Hello Jo",
        reference=str(notification_id)
    )
    persisted_notification = notifications_dao.get_notification(
        sample_template_with_placeholders.service_id, notification_id
    )
    assert persisted_notification.id == notification_id
    assert persisted_notification.to == '+447234123123'
    assert persisted_notification.template_id == sample_template_with_placeholders.id
    assert persisted_notification.status == 'sent'
    assert persisted_notification.created_at == now
    assert persisted_notification.sent_at > now
    assert persisted_notification.sent_by == 'firetext'
    assert not persisted_notification.job_id


def test_should_send_sms_without_personalisation(sample_template, mocker):
    notification = {
        "template": sample_template.id,
        "to": "+447234123123"
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
        now.strftime(DATETIME_FORMAT)
    )

    firetext_client.send_sms.assert_called_once_with(
        to=format_phone_number(validate_phone_number("+447234123123")),
        content="Sample service: This is a template",
        reference=str(notification_id)
    )


def test_should_send_sms_if_restricted_service_and_valid_number(notify_db, notify_db_session, mocker):
    user = sample_user(notify_db, notify_db_session, mobile_numnber="07700 900890")
    service = sample_service(notify_db, notify_db_session, user=user, restricted=True)
    template = sample_template(notify_db, notify_db_session, service=service)

    notification = {
        "template": template.id,
        "to": "+447700900890"  # The user’s own number, but in a different format
    }
    mocker.patch('app.encryption.decrypt', return_value=notification)
    mocker.patch('app.firetext_client.send_sms')
    mocker.patch('app.firetext_client.get_name', return_value="firetext")

    notification_id = uuid.uuid4()
    now = datetime.utcnow()
    send_sms(
        service.id,
        notification_id,
        "encrypted-in-reality",
        now.strftime(DATETIME_FORMAT)
    )

    firetext_client.send_sms.assert_called_once_with(
        to=format_phone_number(validate_phone_number("+447700900890")),
        content="Sample service: This is a template",
        reference=str(notification_id)
    )


def test_should_not_send_sms_if_restricted_service_and_invalid_number(notify_db, notify_db_session, mocker):
    user = sample_user(notify_db, notify_db_session, mobile_numnber="07700 900205")
    service = sample_service(notify_db, notify_db_session, user=user, restricted=True)
    template = sample_template(notify_db, notify_db_session, service=service)

    notification = {
        "template": template.id,
        "to": "07700 900849"
    }
    mocker.patch('app.encryption.decrypt', return_value=notification)
    mocker.patch('app.firetext_client.send_sms')
    mocker.patch('app.firetext_client.get_name', return_value="firetext")

    notification_id = uuid.uuid4()
    now = datetime.utcnow()
    send_sms(
        service.id,
        notification_id,
        "encrypted-in-reality",
        now.strftime(DATETIME_FORMAT)
    )

    firetext_client.send_sms.assert_not_called()


def test_should_send_email_if_restricted_service_and_valid_email(notify_db, notify_db_session, mocker):
    user = sample_user(notify_db, notify_db_session, email="test@restricted.com")
    service = sample_service(notify_db, notify_db_session, user=user, restricted=True)
    template = sample_template(notify_db, notify_db_session, service=service)

    notification = {
        "template": template.id,
        "to": "test@restricted.com"
    }
    mocker.patch('app.encryption.decrypt', return_value=notification)
    mocker.patch('app.aws_ses_client.send_email')

    notification_id = uuid.uuid4()
    now = datetime.utcnow()
    send_email(
        service.id,
        notification_id,
        'subject',
        'email_from',
        "encrypted-in-reality",
        now.strftime(DATETIME_FORMAT)
    )

    aws_ses_client.send_email.assert_called_once_with(
        "email_from",
        "test@restricted.com",
        "subject",
        body=template.content,
        html_body=AnyStringWith(template.content)
    )


def test_should_not_send_email_if_restricted_service_and_invalid_email_address(notify_db, notify_db_session, mocker):
    user = sample_user(notify_db, notify_db_session)
    service = sample_service(notify_db, notify_db_session, user=user, restricted=True)
    template = sample_template(
        notify_db, notify_db_session, service=service, template_type='email', subject_line='Hello'
    )

    notification = {
        "template": template.id,
        "to": "test@example.com"
    }
    mocker.patch('app.encryption.decrypt', return_value=notification)
    mocker.patch('app.aws_ses_client.send_email')

    notification_id = uuid.uuid4()
    now = datetime.utcnow()
    send_sms(
        service.id,
        notification_id,
        "encrypted-in-reality",
        now.strftime(DATETIME_FORMAT)
    )

    aws_ses_client.send_email.assert_not_called()


def test_should_send_template_to_correct_sms_provider_and_persist_with_job_id(sample_job, mocker):
    notification = {
        "template": sample_job.template.id,
        "job": sample_job.id,
        "to": "+447234123123"
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
        now.strftime(DATETIME_FORMAT)
    )
    firetext_client.send_sms.assert_called_once_with(
        to=format_phone_number(validate_phone_number("+447234123123")),
        content="Sample service: This is a template",
        reference=str(notification_id)
    )
    persisted_notification = notifications_dao.get_notification(sample_job.template.service_id, notification_id)
    assert persisted_notification.id == notification_id
    assert persisted_notification.to == '+447234123123'
    assert persisted_notification.job_id == sample_job.id
    assert persisted_notification.template_id == sample_job.template.id
    assert persisted_notification.status == 'sent'
    assert persisted_notification.sent_at > now
    assert persisted_notification.created_at == now
    assert persisted_notification.sent_by == 'firetext'


def test_should_use_email_template_and_persist(sample_email_template_with_placeholders, mocker):
    notification = {
        "template": sample_email_template_with_placeholders.id,
        "to": "my_email@my_email.com",
        "personalisation": {"name": "Jo"}
    }
    mocker.patch('app.encryption.decrypt', return_value=notification)
    mocker.patch('app.aws_ses_client.send_email')
    mocker.patch('app.aws_ses_client.get_name', return_value='ses')

    notification_id = uuid.uuid4()
    now = datetime.utcnow()
    send_email(
        sample_email_template_with_placeholders.service_id,
        notification_id,
        'subject',
        'email_from',
        "encrypted-in-reality",
        now.strftime(DATETIME_FORMAT)
    )
    aws_ses_client.send_email.assert_called_once_with(
        "email_from",
        "my_email@my_email.com",
        "subject",
        body="Hello Jo",
        html_body=AnyStringWith("Hello Jo")
    )
    persisted_notification = notifications_dao.get_notification(
        sample_email_template_with_placeholders.service_id, notification_id
    )
    assert persisted_notification.id == notification_id
    assert persisted_notification.to == 'my_email@my_email.com'
    assert persisted_notification.template_id == sample_email_template_with_placeholders.id
    assert persisted_notification.created_at == now
    assert persisted_notification.sent_at > now
    assert persisted_notification.status == 'sent'
    assert persisted_notification.sent_by == 'ses'


def test_should_use_email_template_and_persist_ses_reference(sample_email_template_with_placeholders, mocker):
    notification = {
        "template": sample_email_template_with_placeholders.id,
        "to": "my_email@my_email.com",
        "personalisation": {"name": "Jo"}
    }
    mocker.patch('app.encryption.decrypt', return_value=notification)
    mocker.patch('app.aws_ses_client.send_email', return_value='reference')

    notification_id = uuid.uuid4()
    now = datetime.utcnow()
    send_email(
        sample_email_template_with_placeholders.service_id,
        notification_id,
        'subject',
        'email_from',
        "encrypted-in-reality",
        now.strftime(DATETIME_FORMAT)
    )
    persisted_notification = notifications_dao.get_notification(
        sample_email_template_with_placeholders.service_id, notification_id
    )
    assert persisted_notification.reference == 'reference'


def test_should_use_email_template_and_persist_without_personalisation(
        sample_email_template, mocker
):
    mocker.patch('app.encryption.decrypt', return_value={
        "template": sample_email_template.id,
        "to": "my_email@my_email.com",
    })
    mocker.patch('app.aws_ses_client.send_email', return_value="ref")
    mocker.patch('app.aws_ses_client.get_name', return_value='ses')

    notification_id = uuid.uuid4()
    now = datetime.utcnow()
    send_email(
        sample_email_template.service_id,
        notification_id,
        'subject',
        'email_from',
        "encrypted-in-reality",
        now.strftime(DATETIME_FORMAT)
    )
    aws_ses_client.send_email.assert_called_once_with(
        "email_from",
        "my_email@my_email.com",
        "subject",
        body="This is a template",
        html_body=AnyStringWith("This is a template")
    )


def test_should_persist_notification_as_failed_if_sms_client_fails(sample_template, mocker):
    notification = {
        "template": sample_template.id,
        "to": "+447234123123"
    }
    mocker.patch('app.encryption.decrypt', return_value=notification)
    mocker.patch('app.firetext_client.send_sms', side_effect=FiretextClientException(firetext_error()))
    mocker.patch('app.firetext_client.get_name', return_value="firetext")
    now = datetime.utcnow()

    notification_id = uuid.uuid4()

    send_sms(
        sample_template.service_id,
        notification_id,
        "encrypted-in-reality",
        now.strftime(DATETIME_FORMAT)
    )
    firetext_client.send_sms.assert_called_once_with(
        to=format_phone_number(validate_phone_number("+447234123123")),
        content="Sample service: This is a template",
        reference=str(notification_id)
    )
    persisted_notification = notifications_dao.get_notification(sample_template.service_id, notification_id)
    assert persisted_notification.id == notification_id
    assert persisted_notification.to == '+447234123123'
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
        now.strftime(DATETIME_FORMAT)
    )
    aws_ses_client.send_email.assert_called_once_with(
        "email_from",
        "my_email@my_email.com",
        "subject",
        body=sample_email_template.content,
        html_body=AnyStringWith(sample_email_template.content)
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
        "to": "+447234123123"
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
        now.strftime(DATETIME_FORMAT)
    )
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
        now.strftime(DATETIME_FORMAT)
    )
    aws_ses_client.send_email.assert_not_called()
    with pytest.raises(NoResultFound) as e:
        notifications_dao.get_notification(sample_email_template.service_id, notification_id)
    assert 'No row was found for one' in str(e.value)


def test_should_send_sms_code(mocker):
    notification = {'to': '+447234123123',
                    'secret_code': '12345'}

    encrypted_notification = encryption.encrypt(notification)

    mocker.patch('app.firetext_client.send_sms')
    send_sms_code(encrypted_notification)
    firetext_client.send_sms.assert_called_once_with(format_phone_number(validate_phone_number(notification['to'])),
                                                     notification['secret_code'],
                                                     'send-sms-code')


def test_should_throw_firetext_client_exception(mocker):
    notification = {'to': '+447234123123',
                    'secret_code': '12345'}

    encrypted_notification = encryption.encrypt(notification)
    mocker.patch('app.firetext_client.send_sms', side_effect=FiretextClientException(firetext_error()))
    send_sms_code(encrypted_notification)
    firetext_client.send_sms.assert_called_once_with(format_phone_number(validate_phone_number(notification['to'])),
                                                     notification['secret_code'],
                                                     'send-sms-code')


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


def test_email_invited_user_should_send_email(notify_api, mocker):
    with notify_api.test_request_context():
        invitation = {'to': 'new_person@it.gov.uk',
                      'user_name': 'John Smith',
                      'service_id': '123123',
                      'service_name': 'Blacksmith Service',
                      'token': 'the-token',
                      'expiry_date': str(datetime.now() + timedelta(days=1))
                      }

        mocker.patch('app.aws_ses_client.send_email')
        mocker.patch('app.encryption.decrypt', return_value=invitation)
        url = tasks.invited_user_url(current_app.config['ADMIN_BASE_URL'], invitation['token'])
        expected_content = tasks.invitation_template(invitation['user_name'],
                                                     invitation['service_name'],
                                                     url,
                                                     invitation['expiry_date'])

        email_invited_user(encryption.encrypt(invitation))
        email_from = "{}@{}".format(current_app.config['INVITATION_EMAIL_FROM'],
                                    current_app.config['NOTIFY_EMAIL_DOMAIN'])
        expected_subject = tasks.invitation_subject_line(invitation['user_name'], invitation['service_name'])
        aws_ses_client.send_email.assert_called_once_with(email_from,
                                                          invitation['to'],
                                                          expected_subject,
                                                          expected_content)


def test_email_reset_password_should_send_email(notify_api, mocker):
    with notify_api.test_request_context():
        reset_password_message = {'to': 'someone@it.gov.uk',
                                  'name': 'Some One',
                                  'reset_password_url': 'bah'}

        mocker.patch('app.aws_ses_client.send_email')
        mocker.patch('app.encryption.decrypt', return_value=reset_password_message)

        encrypted_message = encryption.encrypt(reset_password_message)
        email_reset_password(encrypted_message)
        message = tasks.password_reset_message(reset_password_message['name'],
                                               reset_password_message['reset_password_url'])
        aws_ses_client.send_email(current_app.config['VERIFY_CODE_FROM_EMAIL_ADDRESS'],
                                  reset_password_message['to'],
                                  "Reset password for GOV.UK Notify",
                                  message)
