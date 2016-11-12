import uuid
import pytest
from datetime import datetime

from freezegun import freeze_time
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm.exc import NoResultFound

from app import (encryption, DATETIME_FORMAT)
from app.celery import provider_tasks
from app.celery import tasks
from app.celery.tasks import s3
from app.celery.tasks import (
    send_sms,
    process_job,
    send_email
)
from app.dao import jobs_dao, services_dao
from app.models import Notification, KEY_TYPE_TEAM, KEY_TYPE_TEST, KEY_TYPE_NORMAL
from tests.app import load_example_csv
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


mmg_error = {'Error': '40', 'Description': 'error'}


def _notification_json(template, to, personalisation=None, job_id=None, row_number=None):
    notification = {
        "template": str(template.id),
        "template_version": template.version,
        "to": to,
        "notification_type": template.template_type
    }
    if personalisation:
        notification.update({"personalisation": personalisation})
    if job_id:
        notification.update({"job": str(job_id)})
    if row_number:
        notification['row_number'] = row_number
    return notification


def test_should_have_decorated_tasks_functions():
    assert process_job.__wrapped__.__name__ == 'process_job'
    assert send_sms.__wrapped__.__name__ == 'send_sms'
    assert send_email.__wrapped__.__name__ == 'send_email'


@freeze_time("2016-01-01 11:09:00.061258")
def test_should_process_sms_job(sample_job, mocker):
    mocker.patch('app.celery.tasks.s3.get_job_from_s3', return_value=load_example_csv('sms'))
    mocker.patch('app.celery.tasks.send_sms.apply_async')
    mocker.patch('app.encryption.encrypt', return_value="something_encrypted")
    mocker.patch('app.celery.tasks.create_uuid', return_value="uuid")

    process_job(sample_job.id)
    s3.get_job_from_s3.assert_called_once_with(
        str(sample_job.service.id),
        str(sample_job.id)
    )
    assert encryption.encrypt.call_args[0][0]['to'] == '+441234123123'
    assert encryption.encrypt.call_args[0][0]['template'] == str(sample_job.template.id)
    assert encryption.encrypt.call_args[0][0]['template_version'] == sample_job.template.version
    assert encryption.encrypt.call_args[0][0]['personalisation'] == {}
    assert encryption.encrypt.call_args[0][0]['row_number'] == 0
    tasks.send_sms.apply_async.assert_called_once_with(
        (str(sample_job.service_id),
         "uuid",
         "something_encrypted",
         "2016-01-01T11:09:00.061258"),
        queue="db-sms"
    )
    job = jobs_dao.dao_get_job_by_id(sample_job.id)
    assert job.job_status == 'finished'


@freeze_time("2016-01-01 11:09:00.061258")
def test_should_process_sms_job_into_research_mode_queue_if_research_mode_service(notify_db, notify_db_session, mocker):
    mocker.patch('app.celery.tasks.s3.get_job_from_s3', return_value=load_example_csv('sms'))
    mocker.patch('app.celery.tasks.send_sms.apply_async')
    mocker.patch('app.encryption.encrypt', return_value="something_encrypted")
    mocker.patch('app.celery.tasks.create_uuid', return_value="uuid")

    service = sample_service(notify_db, notify_db_session)
    service.research_mode = True
    services_dao.dao_update_service(service)
    job = sample_job(notify_db, notify_db_session, service=service)

    process_job(job.id)
    s3.get_job_from_s3.assert_called_once_with(
        str(job.service.id),
        str(job.id)
    )
    tasks.send_sms.apply_async.assert_called_once_with(
        (str(job.service_id),
         "uuid",
         "something_encrypted",
         "2016-01-01T11:09:00.061258"),
        queue="research-mode"
    )


@freeze_time("2016-01-01 11:09:00.061258")
def test_should_process_email_job_into_research_mode_queue_if_research_mode_service(
        notify_db, notify_db_session, mocker
):
    mocker.patch('app.celery.tasks.s3.get_job_from_s3', return_value=load_example_csv('sms'))
    mocker.patch('app.celery.tasks.send_email.apply_async')
    mocker.patch('app.encryption.encrypt', return_value="something_encrypted")
    mocker.patch('app.celery.tasks.create_uuid', return_value="uuid")

    service = sample_service(notify_db, notify_db_session)
    service.research_mode = True
    services_dao.dao_update_service(service)
    template = sample_email_template(notify_db, notify_db_session, service=service)
    job = sample_job(notify_db, notify_db_session, template=template, service=service)

    process_job(job.id)
    s3.get_job_from_s3.assert_called_once_with(
        str(job.service.id),
        str(job.id)
    )
    tasks.send_email.apply_async.assert_called_once_with(
        (str(job.service_id),
         "uuid",
         "something_encrypted",
         "2016-01-01T11:09:00.061258"),
        queue="research-mode"
    )


@freeze_time("2016-01-01 11:09:00.061258")
def test_should_not_process_sms_job_if_would_exceed_send_limits(notify_db,
                                                                notify_db_session,
                                                                mocker):
    service = sample_service(notify_db, notify_db_session, limit=9)
    job = sample_job(notify_db, notify_db_session, service=service, notification_count=10)

    mocker.patch('app.celery.tasks.s3.get_job_from_s3', return_value=load_example_csv('multiple_sms'))
    mocker.patch('app.celery.tasks.send_sms.apply_async')
    mocker.patch('app.encryption.encrypt', return_value="something_encrypted")
    mocker.patch('app.celery.tasks.create_uuid', return_value="uuid")

    process_job(job.id)

    job = jobs_dao.dao_get_job_by_id(job.id)
    assert job.job_status == 'sending limits exceeded'
    assert s3.get_job_from_s3.called is False
    assert tasks.send_sms.apply_async.called is False


def test_should_not_process_sms_job_if_would_exceed_send_limits_inc_today(notify_db,
                                                                          notify_db_session,
                                                                          mocker):
    service = sample_service(notify_db, notify_db_session, limit=1)
    job = sample_job(notify_db, notify_db_session, service=service)

    sample_notification(notify_db, notify_db_session, service=service, job=job)

    mocker.patch('app.celery.tasks.s3.get_job_from_s3', return_value=load_example_csv('sms'))
    mocker.patch('app.celery.tasks.send_sms.apply_async')
    mocker.patch('app.encryption.encrypt', return_value="something_encrypted")
    mocker.patch('app.celery.tasks.create_uuid', return_value="uuid")

    process_job(job.id)

    job = jobs_dao.dao_get_job_by_id(job.id)
    assert job.job_status == 'sending limits exceeded'
    assert s3.get_job_from_s3.called is False
    assert tasks.send_sms.apply_async.called is False


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
    assert job.job_status == 'sending limits exceeded'
    assert s3.get_job_from_s3.called is False
    assert tasks.send_email.apply_async.called is False


@freeze_time("2016-01-01 11:09:00.061258")
def test_should_not_process_email_job_if_would_exceed_send_limits(notify_db, notify_db_session, mocker):
    service = sample_service(notify_db, notify_db_session, limit=0)
    template = sample_email_template(notify_db, notify_db_session, service=service)
    job = sample_job(notify_db, notify_db_session, service=service, template=template)

    mocker.patch('app.celery.tasks.s3.get_job_from_s3')
    mocker.patch('app.celery.tasks.send_email.apply_async')
    mocker.patch('app.encryption.encrypt', return_value="something_encrypted")
    mocker.patch('app.celery.tasks.create_uuid', return_value="uuid")

    process_job(job.id)

    job = jobs_dao.dao_get_job_by_id(job.id)
    assert job.job_status == 'sending limits exceeded'
    assert s3.get_job_from_s3.called is False
    assert tasks.send_email.apply_async.called is False


def test_should_not_process_job_if_already_pending(notify_db, notify_db_session, mocker):
    job = sample_job(notify_db, notify_db_session, job_status='scheduled')

    mocker.patch('app.celery.tasks.s3.get_job_from_s3')
    mocker.patch('app.celery.tasks.send_sms.apply_async')

    process_job(job.id)

    assert s3.get_job_from_s3.called is False
    assert tasks.send_sms.apply_async.called is False


@freeze_time("2016-01-01 11:09:00.061258")
def test_should_process_email_job_if_exactly_on_send_limits(notify_db,
                                                            notify_db_session,
                                                            mocker):
    service = sample_service(notify_db, notify_db_session, limit=10)
    template = sample_email_template(notify_db, notify_db_session, service=service)
    job = sample_job(notify_db, notify_db_session, service=service, template=template, notification_count=10)

    mocker.patch('app.celery.tasks.s3.get_job_from_s3', return_value=load_example_csv('multiple_email'))
    mocker.patch('app.celery.tasks.send_email.apply_async')
    mocker.patch('app.encryption.encrypt', return_value="something_encrypted")
    mocker.patch('app.celery.tasks.create_uuid', return_value="uuid")

    process_job(job.id)

    s3.get_job_from_s3.assert_called_once_with(
        str(job.service.id),
        str(job.id)
    )
    job = jobs_dao.dao_get_job_by_id(job.id)
    assert job.job_status == 'finished'
    tasks.send_email.apply_async.assert_called_with(
        (
            str(job.service_id),
            "uuid",
            "something_encrypted",
            "2016-01-01T11:09:00.061258"
        ),
        queue="db-email"
    )


def test_should_not_create_send_task_for_empty_file(sample_job, mocker):
    mocker.patch('app.celery.tasks.s3.get_job_from_s3', return_value=load_example_csv('empty'))
    mocker.patch('app.celery.tasks.send_sms.apply_async')

    process_job(sample_job.id)

    s3.get_job_from_s3.assert_called_once_with(
        str(sample_job.service.id),
        str(sample_job.id)
    )
    job = jobs_dao.dao_get_job_by_id(sample_job.id)
    assert job.job_status == 'finished'


@freeze_time("2016-01-01 11:09:00.061258")
def test_should_process_email_job(sample_email_job, mocker):
    mocker.patch('app.celery.tasks.s3.get_job_from_s3', return_value=load_example_csv('email'))
    mocker.patch('app.celery.tasks.send_email.apply_async')
    mocker.patch('app.encryption.encrypt', return_value="something_encrypted")
    mocker.patch('app.celery.tasks.create_uuid', return_value="uuid")

    process_job(sample_email_job.id)

    s3.get_job_from_s3.assert_called_once_with(
        str(sample_email_job.service.id),
        str(sample_email_job.id)
    )
    assert encryption.encrypt.call_args[0][0]['to'] == 'test@test.com'
    assert encryption.encrypt.call_args[0][0]['template'] == str(sample_email_job.template.id)
    assert encryption.encrypt.call_args[0][0]['template_version'] == sample_email_job.template.version
    assert encryption.encrypt.call_args[0][0]['personalisation'] == {}
    tasks.send_email.apply_async.assert_called_once_with(
        (
            str(sample_email_job.service_id),
            "uuid",
            "something_encrypted",
            "2016-01-01T11:09:00.061258"
        ),
        queue="db-email"
    )
    job = jobs_dao.dao_get_job_by_id(sample_email_job.id)
    assert job.job_status == 'finished'


def test_should_process_all_sms_job(sample_job,
                                    sample_job_with_placeholdered_template,
                                    mocker):
    mocker.patch('app.celery.tasks.s3.get_job_from_s3', return_value=load_example_csv('multiple_sms'))
    mocker.patch('app.celery.tasks.send_sms.apply_async')
    mocker.patch('app.encryption.encrypt', return_value="something_encrypted")
    mocker.patch('app.celery.tasks.create_uuid', return_value="uuid")

    process_job(sample_job_with_placeholdered_template.id)

    s3.get_job_from_s3.assert_called_once_with(
        str(sample_job_with_placeholdered_template.service.id),
        str(sample_job_with_placeholdered_template.id)
    )
    assert encryption.encrypt.call_args[0][0]['to'] == '+441234123120'
    assert encryption.encrypt.call_args[0][0]['template'] == str(sample_job_with_placeholdered_template.template.id)
    assert encryption.encrypt.call_args[0][0][
               'template_version'] == sample_job_with_placeholdered_template.template.version  # noqa
    assert encryption.encrypt.call_args[0][0]['personalisation'] == {'name': 'chris'}
    tasks.send_sms.apply_async.call_count == 10
    job = jobs_dao.dao_get_job_by_id(sample_job_with_placeholdered_template.id)
    assert job.job_status == 'finished'


def test_should_send_template_to_correct_sms_task_and_persist(sample_template_with_placeholders, mocker):
    with freeze_time("2016-01-01 12:00:00.000000"):
        notification = _notification_json(sample_template_with_placeholders,
                                          to="+447234123123", personalisation={"name": "Jo"})

        mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')
        redis_mock = mocker.patch('app.celery.tasks.redis_store.incr')

        notification_id = uuid.uuid4()

        send_sms(
            sample_template_with_placeholders.service_id,
            notification_id,
            encryption.encrypt(notification),
            datetime.utcnow().strftime(DATETIME_FORMAT)
        )

        provider_tasks.deliver_sms.apply_async.assert_called_once_with(
            [notification_id],
            queue="send-sms"
        )

        persisted_notification = Notification.query.filter_by(id=notification_id).one()
        assert persisted_notification.id == notification_id
        assert persisted_notification.to == '+447234123123'
        assert persisted_notification.template_id == sample_template_with_placeholders.id
        assert persisted_notification.template_version == sample_template_with_placeholders.version
        assert persisted_notification.status == 'created'
        assert persisted_notification.created_at <= datetime.utcnow()
        assert not persisted_notification.sent_at
        assert not persisted_notification.sent_by
        assert not persisted_notification.job_id
        assert persisted_notification.personalisation == {'name': 'Jo'}
        assert persisted_notification._personalisation == encryption.encrypt({"name": "Jo"})
        assert persisted_notification.notification_type == 'sms'
        redis_mock.assert_called_with(str(sample_template_with_placeholders.service_id) + '-2016-01-01-count')


def test_should_put_send_sms_task_in_research_mode_queue_if_research_mode_service(notify_db, notify_db_session, mocker):
    service = sample_service(notify_db, notify_db_session)
    service.research_mode = True
    services_dao.dao_update_service(service)

    template = sample_template(notify_db, notify_db_session, service=service)

    notification = _notification_json(template, to="+447234123123")

    mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')

    notification_id = uuid.uuid4()

    send_sms(
        template.service_id,
        notification_id,
        encryption.encrypt(notification),
        datetime.utcnow().strftime(DATETIME_FORMAT)
    )

    provider_tasks.deliver_sms.apply_async.assert_called_once_with(
        [notification_id],
        queue="research-mode"
    )


def test_should_send_sms_if_restricted_service_and_valid_number(notify_db, notify_db_session, mocker):
    user = sample_user(notify_db, notify_db_session, mobile_numnber="07700 900890")
    service = sample_service(notify_db, notify_db_session, user=user, restricted=True)
    template = sample_template(notify_db, notify_db_session, service=service)
    notification = _notification_json(template, "+447700900890")  # The user’s own number, but in a different format

    mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')

    notification_id = uuid.uuid4()
    encrypt_notification = encryption.encrypt(notification)
    send_sms(
        service.id,
        notification_id,
        encrypt_notification,
        datetime.utcnow().strftime(DATETIME_FORMAT)
    )

    provider_tasks.deliver_sms.apply_async.assert_called_once_with(
        [notification_id],
        queue="send-sms"
    )

    persisted_notification = Notification.query.filter_by(id=notification_id).one()
    assert persisted_notification.id == notification_id
    assert persisted_notification.to == '+447700900890'
    assert persisted_notification.template_id == template.id
    assert persisted_notification.template_version == template.version
    assert persisted_notification.status == 'created'
    assert persisted_notification.created_at <= datetime.utcnow()
    assert not persisted_notification.sent_at
    assert not persisted_notification.sent_by
    assert not persisted_notification.job_id
    assert not persisted_notification.personalisation
    assert persisted_notification.notification_type == 'sms'


def test_should_not_send_sms_if_restricted_service_and_invalid_number_with_test_key(notify_db,
                                                                                    notify_db_session,
                                                                                    mocker):
    user = sample_user(notify_db, notify_db_session, mobile_numnber="07700 900205")
    service = sample_service(notify_db, notify_db_session, user=user, restricted=True)
    template = sample_template(notify_db, notify_db_session, service=service)

    notification = _notification_json(template, "07700 900849")
    mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')

    notification_id = uuid.uuid4()
    send_sms(
        service.id,
        notification_id,
        encryption.encrypt(notification),
        datetime.utcnow().strftime(DATETIME_FORMAT),
        key_type=KEY_TYPE_TEST
    )

    provider_tasks.deliver_sms.apply_async.assert_called_once_with(
        [notification_id],
        queue="send-sms"
    )

    persisted_notification = Notification.query.filter_by(id=notification_id).one()
    assert persisted_notification.id == notification_id


def test_should_not_send_email_if_restricted_service_and_invalid_email_address_with_test_key(notify_db,
                                                                                             notify_db_session,
                                                                                             mocker):
    user = sample_user(notify_db, notify_db_session)
    service = sample_service(notify_db, notify_db_session, user=user, restricted=True)
    template = sample_template(
        notify_db, notify_db_session, service=service, template_type='email', subject_line='Hello'
    )

    notification = _notification_json(template, to="test@example.com")
    mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')

    notification_id = uuid.uuid4()
    send_email(
        service.id,
        notification_id,
        encryption.encrypt(notification),
        datetime.utcnow().strftime(DATETIME_FORMAT),
        key_type=KEY_TYPE_TEST
    )

    provider_tasks.deliver_email.apply_async.assert_called_once_with(
        [notification_id],
        queue="send-email"
    )

    persisted_notification = Notification.query.filter_by(id=notification_id).one()
    assert persisted_notification.id == notification_id


def test_should_not_send_sms_if_restricted_service_and_invalid_number(notify_db, notify_db_session, mocker):
    user = sample_user(notify_db, notify_db_session, mobile_numnber="07700 900205")
    service = sample_service(notify_db, notify_db_session, user=user, restricted=True)
    template = sample_template(notify_db, notify_db_session, service=service)

    notification = _notification_json(template, "07700 900849")
    mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')

    notification_id = uuid.uuid4()
    send_sms(
        service.id,
        notification_id,
        encryption.encrypt(notification),
        datetime.utcnow().strftime(DATETIME_FORMAT)
    )
    assert provider_tasks.deliver_sms.apply_async.called is False
    with pytest.raises(NoResultFound):
        Notification.query.filter_by(id=notification_id).one()


def test_should_not_send_email_if_restricted_service_and_invalid_email_address(notify_db, notify_db_session, mocker):
    user = sample_user(notify_db, notify_db_session)
    service = sample_service(notify_db, notify_db_session, user=user, restricted=True)
    template = sample_template(
        notify_db, notify_db_session, service=service, template_type='email', subject_line='Hello'
    )
    notification = _notification_json(template, to="test@example.com")

    notification_id = uuid.uuid4()
    send_email(
        service.id,
        notification_id,
        encryption.encrypt(notification),
        datetime.utcnow().strftime(DATETIME_FORMAT)
    )

    with pytest.raises(NoResultFound):
        Notification.query.filter_by(id=notification_id).one()


def test_should_not_not_increment_counter_if_not_sending_sms(notify_db, notify_db_session, mocker):
    redis_mock = mocker.patch('app.celery.tasks.redis_store.incr')

    user = sample_user(notify_db, notify_db_session)
    service = sample_service(notify_db, notify_db_session, user=user, restricted=True)
    template = sample_template(
        notify_db, notify_db_session, service=service, template_type='sms'
    )
    notification = _notification_json(template, to="+447878787878")

    notification_id = uuid.uuid4()
    send_sms(
        service.id,
        notification_id,
        encryption.encrypt(notification),
        datetime.utcnow().strftime(DATETIME_FORMAT)
    )

    redis_mock.assert_not_called()


def test_should_not_not_increment_counter_if_not_sending_email(notify_db, notify_db_session, mocker):
    redis_mock = mocker.patch('app.celery.tasks.redis_store.incr')

    user = sample_user(notify_db, notify_db_session)
    service = sample_service(notify_db, notify_db_session, user=user, restricted=True)
    template = sample_template(
        notify_db, notify_db_session, service=service, template_type='email', subject_line='Hello'
    )
    notification = _notification_json(template, to="test@example.com")

    notification_id = uuid.uuid4()
    send_email(
        service.id,
        notification_id,
        encryption.encrypt(notification),
        datetime.utcnow().strftime(DATETIME_FORMAT)
    )

    redis_mock.assert_not_called()


def test_should_put_send_email_task_in_research_mode_queue_if_research_mode_service(
        notify_db, notify_db_session, mocker
):
    service = sample_service(notify_db, notify_db_session)
    service.research_mode = True
    services_dao.dao_update_service(service)

    template = sample_email_template(notify_db, notify_db_session, service=service)

    notification = _notification_json(template, to="test@test.com")

    mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')

    notification_id = uuid.uuid4()

    send_email(
        template.service_id,
        notification_id,
        encryption.encrypt(notification),
        datetime.utcnow().strftime(DATETIME_FORMAT)
    )

    provider_tasks.deliver_email.apply_async.assert_called_once_with(
        [notification_id],
        queue="research-mode"
    )


def test_should_send_sms_template_to_and_persist_with_job_id(sample_job, sample_api_key, mocker):
    notification = _notification_json(
        sample_job.template,
        to="+447234123123",
        job_id=sample_job.id,
        row_number=2)
    mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')

    notification_id = uuid.uuid4()
    send_sms(
        sample_job.service.id,
        notification_id,
        encryption.encrypt(notification),
        datetime.utcnow().strftime(DATETIME_FORMAT),
        api_key_id=str(sample_api_key.id),
        key_type=KEY_TYPE_NORMAL
    )
    provider_tasks.deliver_sms.apply_async.assert_called_once_with(
        [notification_id],
        queue="send-sms"
    )
    persisted_notification = Notification.query.filter_by(id=notification_id).one()
    assert persisted_notification.id == notification_id
    assert persisted_notification.to == '+447234123123'
    assert persisted_notification.job_id == sample_job.id
    assert persisted_notification.template_id == sample_job.template.id
    assert persisted_notification.status == 'created'
    assert not persisted_notification.sent_at
    assert persisted_notification.created_at <= datetime.utcnow()
    assert not persisted_notification.sent_by
    assert persisted_notification.job_row_number == 2
    assert persisted_notification.api_key_id == sample_api_key.id
    assert persisted_notification.key_type == KEY_TYPE_NORMAL
    assert persisted_notification.notification_type == 'sms'


def test_should_not_send_email_if_team_key_and_recipient_not_in_team(sample_email_template_with_placeholders,
                                                                     sample_team_api_key,
                                                                     mocker):
    notification = _notification_json(
        sample_email_template_with_placeholders,
        "my_email@my_email.com",
        {"name": "Jo"},
        row_number=1)
    apply_async = mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    notification_id = uuid.uuid4()

    team_members = [user.email_address for user in sample_email_template_with_placeholders.service.users]
    assert "my_email@my_email.com" not in team_members

    with freeze_time("2016-01-01 11:09:00.00000"):
        now = datetime.utcnow()

        send_email(
            sample_email_template_with_placeholders.service_id,
            notification_id,
            encryption.encrypt(notification),
            now.strftime(DATETIME_FORMAT),
            api_key_id=str(sample_team_api_key.id),
            key_type=KEY_TYPE_TEAM
        )

        with pytest.raises(NoResultFound):
            persisted_notification = Notification.query.filter_by(id=notification_id).one()
            print(persisted_notification)

    apply_async.not_called()


def test_should_not_send_sms_if_team_key_and_recipient_not_in_team(notify_db, notify_db_session, mocker):
    user = sample_user(notify_db, notify_db_session, mobile_numnber="07700 900205")
    service = sample_service(notify_db, notify_db_session, user=user, restricted=True)
    template = sample_template(notify_db, notify_db_session, service=service)

    team_members = [user.mobile_number for user in service.users]
    assert "07890 300000" not in team_members

    notification = _notification_json(template, "07700 900849")
    mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')

    notification_id = uuid.uuid4()
    send_sms(
        service.id,
        notification_id,
        encryption.encrypt(notification),
        datetime.utcnow().strftime(DATETIME_FORMAT)
    )
    assert provider_tasks.deliver_sms.apply_async.called is False
    with pytest.raises(NoResultFound):
        Notification.query.filter_by(id=notification_id).one()


def test_should_use_email_template_and_persist(sample_email_template_with_placeholders, sample_api_key, mocker):
    with freeze_time("2016-01-01 12:00:00.000000"):
        notification = _notification_json(
            sample_email_template_with_placeholders,
            'my_email@my_email.com',
            {"name": "Jo"},
            row_number=1)
        mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
        redis_mock = mocker.patch('app.celery.tasks.redis_store.incr')

        notification_id = uuid.uuid4()

        with freeze_time("2016-01-01 11:09:00.00000"):
            now = datetime.utcnow()

        with freeze_time("2016-01-01 11:10:00.00000"):
            send_email(
                sample_email_template_with_placeholders.service_id,
                notification_id,
                encryption.encrypt(notification),
                now.strftime(DATETIME_FORMAT),
                api_key_id=str(sample_api_key.id),
                key_type=sample_api_key.key_type
            )

        persisted_notification = Notification.query.filter_by(id=notification_id).one()
        provider_tasks.deliver_email.apply_async.assert_called_once_with(
            [notification_id], queue='send-email')

        assert persisted_notification.id == notification_id
        assert persisted_notification.to == 'my_email@my_email.com'
        assert persisted_notification.template_id == sample_email_template_with_placeholders.id
        assert persisted_notification.template_version == sample_email_template_with_placeholders.version
        assert persisted_notification.created_at == now
        assert not persisted_notification.sent_at
        assert persisted_notification.status == 'created'
        assert not persisted_notification.sent_by
        assert persisted_notification.job_row_number == 1
        assert persisted_notification.personalisation == {'name': 'Jo'}
        assert persisted_notification._personalisation == encryption.encrypt({"name": "Jo"})
        assert persisted_notification.api_key_id == sample_api_key.id
        assert persisted_notification.key_type == KEY_TYPE_NORMAL
        assert persisted_notification.notification_type == 'email'
        redis_mock.assert_called_with(str(sample_email_template_with_placeholders.service_id) + '-2016-01-01-count')


def test_send_email_should_use_template_version_from_job_not_latest(sample_email_template, mocker):
    notification = _notification_json(sample_email_template, 'my_email@my_email.com')
    version_on_notification = sample_email_template.version
    # Change the template
    from app.dao.templates_dao import dao_update_template, dao_get_template_by_id
    sample_email_template.content = sample_email_template.content + " another version of the template"
    mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    dao_update_template(sample_email_template)
    t = dao_get_template_by_id(sample_email_template.id)
    assert t.version > version_on_notification
    notification_id = uuid.uuid4()
    now = datetime.utcnow()
    send_email(
        sample_email_template.service_id,
        notification_id,
        encryption.encrypt(notification),
        now.strftime(DATETIME_FORMAT)
    )

    provider_tasks.deliver_email.apply_async.assert_called_once_with([notification_id], queue='send-email')

    persisted_notification = Notification.query.filter_by(id=notification_id).one()
    assert persisted_notification.id == notification_id
    assert persisted_notification.to == 'my_email@my_email.com'
    assert persisted_notification.template_id == sample_email_template.id
    assert persisted_notification.template_version == version_on_notification
    assert persisted_notification.created_at == now
    assert not persisted_notification.sent_at
    assert persisted_notification.status == 'created'
    assert not persisted_notification.sent_by
    assert persisted_notification.notification_type == 'email'


def test_should_use_email_template_subject_placeholders(sample_email_template_with_placeholders, mocker):
    notification = _notification_json(sample_email_template_with_placeholders,
                                      "my_email@my_email.com", {"name": "Jo"})
    mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')

    notification_id = uuid.uuid4()
    now = datetime.utcnow()
    send_email(
        sample_email_template_with_placeholders.service_id,
        notification_id,
        encryption.encrypt(notification),
        now.strftime(DATETIME_FORMAT)
    )
    provider_tasks.deliver_email.apply_async.assert_called_once_with(
        [notification_id], queue='send-email'
    )
    persisted_notification = Notification.query.filter_by(id=notification_id).one()
    assert persisted_notification.id == notification_id
    assert persisted_notification.to == 'my_email@my_email.com'
    assert persisted_notification.template_id == sample_email_template_with_placeholders.id
    assert persisted_notification.status == 'created'
    assert not persisted_notification.sent_by
    assert persisted_notification.personalisation == {"name": "Jo"}
    assert not persisted_notification.reference
    assert persisted_notification.notification_type == 'email'


def test_should_use_email_template_and_persist_without_personalisation(sample_email_template, mocker):
    notification = _notification_json(sample_email_template, "my_email@my_email.com")
    mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')

    notification_id = uuid.uuid4()

    now = datetime.utcnow()
    send_email(
        sample_email_template.service_id,
        notification_id,
        encryption.encrypt(notification),
        now.strftime(DATETIME_FORMAT)
    )
    provider_tasks.deliver_email.apply_async.assert_called_once_with([notification_id], queue='send-email')

    persisted_notification = Notification.query.filter_by(id=notification_id).one()
    assert persisted_notification.id == notification_id
    assert persisted_notification.to == 'my_email@my_email.com'
    assert persisted_notification.template_id == sample_email_template.id
    assert persisted_notification.created_at == now
    assert not persisted_notification.sent_at
    assert persisted_notification.status == 'created'
    assert not persisted_notification.sent_by
    assert not persisted_notification.personalisation
    assert not persisted_notification.reference
    assert persisted_notification.notification_type == 'email'


def test_send_sms_should_go_to_retry_queue_if_database_errors(sample_template, mocker):
    notification = _notification_json(sample_template, "+447234123123")

    expected_exception = SQLAlchemyError()

    mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')
    mocker.patch('app.celery.tasks.send_sms.retry', side_effect=Exception())
    mocker.patch('app.celery.tasks.dao_create_notification', side_effect=expected_exception)
    now = datetime.utcnow()

    notification_id = uuid.uuid4()

    with pytest.raises(Exception):
        send_sms(
            sample_template.service_id,
            notification_id,
            encryption.encrypt(notification),
            now.strftime(DATETIME_FORMAT)
        )
    assert provider_tasks.deliver_sms.apply_async.called is False
    tasks.send_sms.retry.assert_called_with(exc=expected_exception, queue='retry')

    with pytest.raises(NoResultFound) as e:
        Notification.query.filter_by(id=notification_id).one()
    assert 'No row was found for one' in str(e.value)


def test_send_email_should_go_to_retry_queue_if_database_errors(sample_email_template, mocker):
    notification = _notification_json(sample_email_template, "test@example.gov.uk")

    expected_exception = SQLAlchemyError()

    mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    mocker.patch('app.celery.tasks.send_email.retry', side_effect=Exception())
    mocker.patch('app.celery.tasks.dao_create_notification', side_effect=expected_exception)
    now = datetime.utcnow()

    notification_id = uuid.uuid4()

    with pytest.raises(Exception):
        send_email(
            sample_email_template.service_id,
            notification_id,
            encryption.encrypt(notification),
            now.strftime(DATETIME_FORMAT)
        )
    assert provider_tasks.deliver_email.apply_async.called is False
    tasks.send_email.retry.assert_called_with(exc=expected_exception, queue='retry')

    with pytest.raises(NoResultFound) as e:
        Notification.query.filter_by(id=notification_id).one()
    assert 'No row was found for one' in str(e.value)
