import uuid
from datetime import datetime
from unittest.mock import Mock

import pytest
from flask import current_app
from freezegun import freeze_time
from sqlalchemy.exc import SQLAlchemyError
from notifications_utils.template import SMSMessageTemplate, WithSubjectTemplate, LetterDVLATemplate
from celery.exceptions import Retry

from app import (encryption, DATETIME_FORMAT)
from app.celery import provider_tasks
from app.celery import tasks
from app.celery.tasks import (
    s3,
    build_dvla_file,
    create_dvla_file_contents,
    update_dvla_job_to_error,
    process_job,
    process_row,
    send_sms,
    send_email,
    persist_letter,
    get_template_class,
    update_job_to_sent_to_dvla,
    update_letter_notifications_statuses,
    process_updates_from_file
)
from app.dao import jobs_dao, services_dao
from app.models import (
    Notification,
    Job)
from app.definitions import (
    KEY_TYPE_TEAM,
    KEY_TYPE_TEST,
    KEY_TYPE_NORMAL,
    SMS_TYPE,
    EMAIL_TYPE,
    LETTER_TYPE
)

from tests.app import load_example_csv
from tests.conftest import set_config
from tests.app.conftest import (
    sample_service,
    sample_template,
    sample_job,
    sample_email_template,
    sample_notification
)
from tests.app.db import create_user, create_notification, create_job


class AnyStringWith(str):
    def __eq__(self, other):
        return self in other


mmg_error = {'Error': '40', 'Description': 'error'}


def _notification_json(template, to, personalisation=None, job_id=None, row_number=0):
    return {
        "template": str(template.id),
        "template_version": template.version,
        "to": to,
        "notification_type": template.template_type,
        "personalisation": personalisation or {},
        "job": job_id and str(job_id),
        "row_number": row_number
    }


def test_should_have_decorated_tasks_functions():
    assert process_job.__wrapped__.__name__ == 'process_job'
    assert send_sms.__wrapped__.__name__ == 'send_sms'
    assert send_email.__wrapped__.__name__ == 'send_email'


@pytest.fixture
def email_job_with_placeholders(notify_db, notify_db_session, sample_email_template_with_placeholders):
    return sample_job(notify_db, notify_db_session, template=sample_email_template_with_placeholders)


# -------------- process_job tests -------------- #


@freeze_time("2016-01-01 11:09:00.061258")
def test_should_process_sms_job(sample_job, mocker):
    mocker.patch('app.celery.tasks.s3.get_job_from_s3', return_value=load_example_csv('sms'))
    mocker.patch('app.celery.tasks.send_sms.apply_async')
    mocker.patch('app.encryption.encrypt', return_value="something_encrypted")
    mocker.patch('app.celery.tasks.build_dvla_file')
    mocker.patch('app.celery.tasks.create_uuid', return_value="uuid")
    mocker.patch('app.celery.tasks.build_dvla_file')

    process_job(sample_job.id)
    s3.get_job_from_s3.assert_called_once_with(
        str(sample_job.service.id),
        str(sample_job.id)
    )
    assert encryption.encrypt.call_args[0][0]['to'] == '+441234123123'
    assert encryption.encrypt.call_args[0][0]['template'] == str(sample_job.template.id)
    assert encryption.encrypt.call_args[0][0]['template_version'] == sample_job.template.version
    assert encryption.encrypt.call_args[0][0]['personalisation'] == {'phonenumber': '+441234123123'}
    assert encryption.encrypt.call_args[0][0]['row_number'] == 0
    tasks.send_sms.apply_async.assert_called_once_with(
        (str(sample_job.service_id),
         "uuid",
         "something_encrypted",
         "2016-01-01T11:09:00.061258Z"),
        queue="database-tasks"
    )
    job = jobs_dao.dao_get_job_by_id(sample_job.id)
    assert job.job_status == 'finished'
    tasks.build_dvla_file.assert_not_called()


@freeze_time("2016-01-01 11:09:00.061258")
def test_should_not_process_sms_job_if_would_exceed_send_limits(notify_db,
                                                                notify_db_session,
                                                                mocker):
    service = sample_service(notify_db, notify_db_session, limit=9)
    job = sample_job(notify_db, notify_db_session, service=service, notification_count=10)

    mocker.patch('app.celery.tasks.s3.get_job_from_s3', return_value=load_example_csv('multiple_sms'))
    mocker.patch('app.celery.tasks.process_row')
    mocker.patch('app.celery.tasks.build_dvla_file')

    process_job(job.id)

    job = jobs_dao.dao_get_job_by_id(job.id)
    assert job.job_status == 'sending limits exceeded'
    assert s3.get_job_from_s3.called is False
    assert tasks.process_row.called is False
    tasks.build_dvla_file.assert_not_called()


def test_should_not_process_sms_job_if_would_exceed_send_limits_inc_today(notify_db,
                                                                          notify_db_session,
                                                                          mocker):
    service = sample_service(notify_db, notify_db_session, limit=1)
    job = sample_job(notify_db, notify_db_session, service=service)

    sample_notification(notify_db, notify_db_session, service=service, job=job)

    mocker.patch('app.celery.tasks.s3.get_job_from_s3', return_value=load_example_csv('sms'))
    mocker.patch('app.celery.tasks.process_row')
    mocker.patch('app.celery.tasks.build_dvla_file')

    process_job(job.id)

    job = jobs_dao.dao_get_job_by_id(job.id)
    assert job.job_status == 'sending limits exceeded'
    assert s3.get_job_from_s3.called is False
    assert tasks.process_row.called is False
    tasks.build_dvla_file.assert_not_called()


def test_should_not_process_email_job_if_would_exceed_send_limits_inc_today(notify_db, notify_db_session, mocker):
    service = sample_service(notify_db, notify_db_session, limit=1)
    template = sample_email_template(notify_db, notify_db_session, service=service)
    job = sample_job(notify_db, notify_db_session, service=service, template=template)

    sample_notification(notify_db, notify_db_session, service=service, job=job)

    mocker.patch('app.celery.tasks.s3.get_job_from_s3')
    mocker.patch('app.celery.tasks.process_row')
    mocker.patch('app.celery.tasks.build_dvla_file')

    process_job(job.id)

    job = jobs_dao.dao_get_job_by_id(job.id)
    assert job.job_status == 'sending limits exceeded'
    assert s3.get_job_from_s3.called is False
    assert tasks.process_row.called is False
    tasks.build_dvla_file.assert_not_called()


@freeze_time("2016-01-01 11:09:00.061258")
def test_should_not_process_email_job_if_would_exceed_send_limits(notify_db, notify_db_session, mocker):
    service = sample_service(notify_db, notify_db_session, limit=0)
    template = sample_email_template(notify_db, notify_db_session, service=service)
    job = sample_job(notify_db, notify_db_session, service=service, template=template)

    mocker.patch('app.celery.tasks.s3.get_job_from_s3')
    mocker.patch('app.celery.tasks.process_row')
    mocker.patch('app.celery.tasks.build_dvla_file')

    process_job(job.id)

    job = jobs_dao.dao_get_job_by_id(job.id)
    assert job.job_status == 'sending limits exceeded'
    assert s3.get_job_from_s3.called is False
    assert tasks.process_row.called is False
    tasks.build_dvla_file.assert_not_called()


def test_should_not_process_job_if_already_pending(notify_db, notify_db_session, mocker):
    job = sample_job(notify_db, notify_db_session, job_status='scheduled')

    mocker.patch('app.celery.tasks.s3.get_job_from_s3')
    mocker.patch('app.celery.tasks.process_row')
    mocker.patch('app.celery.tasks.build_dvla_file')

    process_job(job.id)

    assert s3.get_job_from_s3.called is False
    assert tasks.process_row.called is False
    tasks.build_dvla_file.assert_not_called()


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
            "2016-01-01T11:09:00.061258Z"
        ),
        queue="database-tasks"
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
    assert tasks.send_sms.apply_async.called is False


@freeze_time("2016-01-01 11:09:00.061258")
def test_should_process_email_job(email_job_with_placeholders, mocker):
    email_csv = """email_address,name
    test@test.com,foo
    """
    mocker.patch('app.celery.tasks.s3.get_job_from_s3', return_value=email_csv)
    mocker.patch('app.celery.tasks.send_email.apply_async')
    mocker.patch('app.encryption.encrypt', return_value="something_encrypted")
    mocker.patch('app.celery.tasks.create_uuid', return_value="uuid")

    process_job(email_job_with_placeholders.id)

    s3.get_job_from_s3.assert_called_once_with(
        str(email_job_with_placeholders.service.id),
        str(email_job_with_placeholders.id)
    )
    assert encryption.encrypt.call_args[0][0]['to'] == 'test@test.com'
    assert encryption.encrypt.call_args[0][0]['template'] == str(email_job_with_placeholders.template.id)
    assert encryption.encrypt.call_args[0][0]['template_version'] == email_job_with_placeholders.template.version
    assert encryption.encrypt.call_args[0][0]['personalisation'] == {'emailaddress': 'test@test.com', 'name': 'foo'}
    tasks.send_email.apply_async.assert_called_once_with(
        (
            str(email_job_with_placeholders.service_id),
            "uuid",
            "something_encrypted",
            "2016-01-01T11:09:00.061258Z"
        ),
        queue="database-tasks"
    )
    job = jobs_dao.dao_get_job_by_id(email_job_with_placeholders.id)
    assert job.job_status == 'finished'


@freeze_time("2016-01-01 11:09:00.061258")
def test_should_process_letter_job(sample_letter_job, mocker):
    csv = """address_line_1,address_line_2,address_line_3,address_line_4,postcode,name
    A1,A2,A3,A4,A_POST,Alice
    """
    s3_mock = mocker.patch('app.celery.tasks.s3.get_job_from_s3', return_value=csv)
    mocker.patch('app.celery.tasks.send_email.apply_async')
    process_row_mock = mocker.patch('app.celery.tasks.process_row')
    mocker.patch('app.celery.tasks.create_uuid', return_value="uuid")
    mocker.patch('app.celery.tasks.build_dvla_file')

    process_job(sample_letter_job.id)

    s3_mock.assert_called_once_with(
        str(sample_letter_job.service.id),
        str(sample_letter_job.id)
    )

    row_call = process_row_mock.mock_calls[0][1]

    assert row_call[0] == 0
    assert row_call[1] == ['A1', 'A2', 'A3', 'A4', None, None, 'A_POST']
    assert dict(row_call[2]) == {
        'addressline1': 'A1',
        'addressline2': 'A2',
        'addressline3': 'A3',
        'addressline4': 'A4',
        'postcode': 'A_POST'
    }
    assert row_call[4] == sample_letter_job
    assert row_call[5] == sample_letter_job.service

    assert process_row_mock.call_count == 1

    assert sample_letter_job.job_status == 'in progress'
    tasks.build_dvla_file.apply_async.assert_called_once_with([str(sample_letter_job.id)], queue="job-tasks")


def test_should_process_all_sms_job(sample_job_with_placeholdered_template,
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
    assert encryption.encrypt.call_args[0][0]['personalisation'] == {'phonenumber': '+441234123120', 'name': 'chris'}
    assert tasks.send_sms.apply_async.call_count == 10
    job = jobs_dao.dao_get_job_by_id(sample_job_with_placeholdered_template.id)
    assert job.job_status == 'finished'


# -------------- process_row tests -------------- #


@freeze_time('2001-01-01T12:00:00')
@pytest.mark.parametrize('template_type, research_mode, expected_function, expected_queue', [
    (SMS_TYPE, False, 'send_sms', 'database-tasks'),
    (SMS_TYPE, True, 'send_sms', 'research-mode-tasks'),
    (EMAIL_TYPE, False, 'send_email', 'database-tasks'),
    (EMAIL_TYPE, True, 'send_email', 'research-mode-tasks'),
    (LETTER_TYPE, False, 'persist_letter', 'database-tasks'),
    (LETTER_TYPE, True, 'persist_letter', 'research-mode-tasks'),
])
def test_process_row_sends_letter_task(template_type, research_mode, expected_function, expected_queue, mocker):
    mocker.patch('app.celery.tasks.create_uuid', return_value='noti_uuid')
    task_mock = mocker.patch('app.celery.tasks.{}.apply_async'.format(expected_function))
    encrypt_mock = mocker.patch('app.celery.tasks.encryption.encrypt')
    template = Mock(id='template_id', template_type=template_type)
    job = Mock(id='job_id', template_version='temp_vers')
    service = Mock(id='service_id', research_mode=research_mode)

    process_row('row_num', 'recip', {'foo': 'bar'}, template, job, service)

    encrypt_mock.assert_called_once_with({
        'template': 'template_id',
        'template_version': 'temp_vers',
        'job': 'job_id',
        'to': 'recip',
        'row_number': 'row_num',
        'personalisation': {'foo': 'bar'}
    })
    task_mock.assert_called_once_with(
        (
            'service_id',
            'noti_uuid',
            # encrypted data
            encrypt_mock.return_value,
            '2001-01-01T12:00:00.000000Z'
        ),
        queue=expected_queue
    )
# -------- send_sms and send_email tests -------- #


def test_should_send_template_to_correct_sms_task_and_persist(sample_template_with_placeholders, mocker):
    notification = _notification_json(sample_template_with_placeholders,
                                      to="+447234123123", personalisation={"name": "Jo"})

    mocked_deliver_sms = mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')

    send_sms(
        sample_template_with_placeholders.service_id,
        uuid.uuid4(),
        encryption.encrypt(notification),
        datetime.utcnow().strftime(DATETIME_FORMAT)
    )

    persisted_notification = Notification.query.one()
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
    mocked_deliver_sms.assert_called_once_with(
        [str(persisted_notification.id)],
        queue="send-tasks"
    )


def test_should_put_send_sms_task_in_research_mode_queue_if_research_mode_service(notify_db, notify_db_session, mocker):
    service = sample_service(notify_db, notify_db_session)
    service.research_mode = True
    services_dao.dao_update_service(service)

    template = sample_template(notify_db, notify_db_session, service=service)

    notification = _notification_json(template, to="+447234123123")

    mocked_deliver_sms = mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')

    notification_id = uuid.uuid4()

    send_sms(
        template.service_id,
        notification_id,
        encryption.encrypt(notification),
        datetime.utcnow().strftime(DATETIME_FORMAT)
    )
    persisted_notification = Notification.query.one()
    provider_tasks.deliver_sms.apply_async.assert_called_once_with(
        [str(persisted_notification.id)],
        queue="research-mode-tasks"
    )
    assert mocked_deliver_sms.called


def test_should_send_sms_if_restricted_service_and_valid_number(notify_db, notify_db_session, mocker):
    user = create_user(mobile_number="07700 900890")
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

    persisted_notification = Notification.query.one()
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
    provider_tasks.deliver_sms.apply_async.assert_called_once_with(
        [str(persisted_notification.id)],
        queue="send-tasks"
    )


def test_should_send_sms_if_restricted_service_and_non_team_number_with_test_key(notify_db,
                                                                                 notify_db_session,
                                                                                 mocker):
    user = create_user(mobile_number="07700 900205")
    service = sample_service(notify_db, notify_db_session, user=user, restricted=True)
    template = sample_template(notify_db, notify_db_session, service=service)

    notification = _notification_json(template, "07700 900849")
    mocked_deliver_sms = mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')

    notification_id = uuid.uuid4()
    send_sms(
        service.id,
        notification_id,
        encryption.encrypt(notification),
        datetime.utcnow().strftime(DATETIME_FORMAT),
        key_type=KEY_TYPE_TEST
    )

    persisted_notification = Notification.query.one()
    mocked_deliver_sms.assert_called_once_with(
        [str(persisted_notification.id)],
        queue="send-tasks"
    )


def test_should_send_email_if_restricted_service_and_non_team_email_address_with_test_key(notify_db,
                                                                                          notify_db_session,
                                                                                          mocker):
    user = create_user()
    service = sample_service(notify_db, notify_db_session, user=user, restricted=True)
    template = sample_template(
        notify_db, notify_db_session, service=service, template_type='email', subject_line='Hello'
    )

    notification = _notification_json(template, to="test@example.com")
    mocked_deliver_email = mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')

    notification_id = uuid.uuid4()
    send_email(
        service.id,
        notification_id,
        encryption.encrypt(notification),
        datetime.utcnow().strftime(DATETIME_FORMAT),
        key_type=KEY_TYPE_TEST
    )

    persisted_notification = Notification.query.one()
    mocked_deliver_email.assert_called_once_with(
        [str(persisted_notification.id)],
        queue="send-tasks"
    )


def test_should_not_send_sms_if_restricted_service_and_invalid_number(notify_db, notify_db_session, mocker):
    user = create_user(mobile_number="07700 900205")
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
    assert Notification.query.count() == 0


def test_should_not_send_email_if_restricted_service_and_invalid_email_address(notify_db, notify_db_session, mocker):
    user = create_user()
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

    assert Notification.query.count() == 0


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

    persisted_notification = Notification.query.one()
    provider_tasks.deliver_email.apply_async.assert_called_once_with(
        [str(persisted_notification.id)],
        queue="research-mode-tasks"
    )


def test_should_send_sms_template_to_and_persist_with_job_id(sample_job, sample_api_key, mocker):
    notification = _notification_json(
        sample_job.template,
        to="+447234123123",
        job_id=sample_job.id,
        row_number=2)
    mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')

    notification_id = uuid.uuid4()
    now = datetime.utcnow()
    send_sms(
        sample_job.service.id,
        notification_id,
        encryption.encrypt(notification),
        now.strftime(DATETIME_FORMAT),
        api_key_id=str(sample_api_key.id),
        key_type=KEY_TYPE_NORMAL
    )
    persisted_notification = Notification.query.one()
    assert persisted_notification.to == '+447234123123'
    assert persisted_notification.job_id == sample_job.id
    assert persisted_notification.template_id == sample_job.template.id
    assert persisted_notification.status == 'created'
    assert not persisted_notification.sent_at
    assert persisted_notification.created_at <= now
    assert not persisted_notification.sent_by
    assert persisted_notification.job_row_number == 2
    assert persisted_notification.api_key_id == sample_api_key.id
    assert persisted_notification.key_type == KEY_TYPE_NORMAL
    assert persisted_notification.notification_type == 'sms'

    provider_tasks.deliver_sms.apply_async.assert_called_once_with(
        [str(persisted_notification.id)],
        queue="send-tasks"
    )


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

        assert Notification.query.count() == 0

    apply_async.not_called()


def test_should_not_send_sms_if_team_key_and_recipient_not_in_team(notify_db, notify_db_session, mocker):
    assert Notification.query.count() == 0
    user = create_user(mobile_number="07700 900205")
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
    assert Notification.query.count() == 0


def test_should_use_email_template_and_persist(sample_email_template_with_placeholders, sample_api_key, mocker):
    mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')

    now = datetime(2016, 1, 1, 11, 9, 0)
    notification_id = uuid.uuid4()

    with freeze_time("2016-01-01 12:00:00.000000"):
        notification = _notification_json(
            sample_email_template_with_placeholders,
            'my_email@my_email.com',
            {"name": "Jo"},
            row_number=1)

    with freeze_time("2016-01-01 11:10:00.00000"):
        send_email(
            sample_email_template_with_placeholders.service_id,
            notification_id,
            encryption.encrypt(notification),
            now.strftime(DATETIME_FORMAT),
            api_key_id=str(sample_api_key.id),
            key_type=sample_api_key.key_type
        )

    persisted_notification = Notification.query.one()
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

    provider_tasks.deliver_email.apply_async.assert_called_once_with(
        [str(persisted_notification.id)], queue='send-tasks')


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
    now = datetime.utcnow()
    send_email(
        sample_email_template.service_id,
        uuid.uuid4(),
        encryption.encrypt(notification),
        now.strftime(DATETIME_FORMAT)
    )

    persisted_notification = Notification.query.one()
    assert persisted_notification.to == 'my_email@my_email.com'
    assert persisted_notification.template_id == sample_email_template.id
    assert persisted_notification.template_version == version_on_notification
    assert persisted_notification.created_at == now
    assert not persisted_notification.sent_at
    assert persisted_notification.status == 'created'
    assert not persisted_notification.sent_by
    assert persisted_notification.notification_type == 'email'
    provider_tasks.deliver_email.apply_async.assert_called_once_with([str(persisted_notification.id)],
                                                                     queue='send-tasks')


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
    persisted_notification = Notification.query.one()
    assert persisted_notification.to == 'my_email@my_email.com'
    assert persisted_notification.template_id == sample_email_template_with_placeholders.id
    assert persisted_notification.status == 'created'
    assert persisted_notification.created_at == now
    assert not persisted_notification.sent_by
    assert persisted_notification.personalisation == {"name": "Jo"}
    assert not persisted_notification.reference
    assert persisted_notification.notification_type == 'email'
    provider_tasks.deliver_email.apply_async.assert_called_once_with(
        [str(persisted_notification.id)], queue='send-tasks'
    )


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
    persisted_notification = Notification.query.one()
    assert persisted_notification.to == 'my_email@my_email.com'
    assert persisted_notification.template_id == sample_email_template.id
    assert persisted_notification.created_at == now
    assert not persisted_notification.sent_at
    assert persisted_notification.status == 'created'
    assert not persisted_notification.sent_by
    assert not persisted_notification.personalisation
    assert not persisted_notification.reference
    assert persisted_notification.notification_type == 'email'
    provider_tasks.deliver_email.apply_async.assert_called_once_with([str(persisted_notification.id)],
                                                                     queue='send-tasks')


def test_send_sms_should_go_to_retry_queue_if_database_errors(sample_template, mocker):
    notification = _notification_json(sample_template, "+447234123123")

    expected_exception = SQLAlchemyError()

    mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')
    mocker.patch('app.celery.tasks.send_sms.retry', side_effect=Retry)
    mocker.patch('app.notifications.process_notifications.dao_create_notification', side_effect=expected_exception)
    now = datetime.utcnow()

    notification_id = uuid.uuid4()

    with pytest.raises(Retry):
        send_sms(
            sample_template.service_id,
            notification_id,
            encryption.encrypt(notification),
            now.strftime(DATETIME_FORMAT)
        )
    assert provider_tasks.deliver_sms.apply_async.called is False
    tasks.send_sms.retry.assert_called_with(exc=expected_exception, queue="retry-tasks")

    assert Notification.query.count() == 0


def test_send_email_should_go_to_retry_queue_if_database_errors(sample_email_template, mocker):
    notification = _notification_json(sample_email_template, "test@example.gov.uk")

    expected_exception = SQLAlchemyError()

    mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    mocker.patch('app.celery.tasks.send_email.retry', side_effect=Retry)
    mocker.patch('app.notifications.process_notifications.dao_create_notification', side_effect=expected_exception)
    now = datetime.utcnow()

    notification_id = uuid.uuid4()

    with pytest.raises(Retry):
        send_email(
            sample_email_template.service_id,
            notification_id,
            encryption.encrypt(notification),
            now.strftime(DATETIME_FORMAT)
        )
    assert not provider_tasks.deliver_email.apply_async.called
    tasks.send_email.retry.assert_called_with(exc=expected_exception, queue="retry-tasks")

    assert Notification.query.count() == 0


def test_send_email_does_not_send_duplicate_and_does_not_put_in_retry_queue(sample_notification, mocker):
    json = _notification_json(sample_notification.template, sample_notification.to, job_id=uuid.uuid4(), row_number=1)
    deliver_email = mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    retry = mocker.patch('app.celery.tasks.send_email.retry', side_effect=Exception())
    now = datetime.utcnow()

    notification_id = sample_notification.id

    send_email(
        sample_notification.service_id,
        notification_id,
        encryption.encrypt(json),
        now.strftime(DATETIME_FORMAT)
    )
    assert Notification.query.count() == 1
    assert not deliver_email.called
    assert not retry.called


def test_send_sms_does_not_send_duplicate_and_does_not_put_in_retry_queue(sample_notification, mocker):
    json = _notification_json(sample_notification.template, sample_notification.to, job_id=uuid.uuid4(), row_number=1)
    deliver_sms = mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')
    retry = mocker.patch('app.celery.tasks.send_sms.retry', side_effect=Exception())
    now = datetime.utcnow()

    notification_id = sample_notification.id

    send_sms(
        sample_notification.service_id,
        notification_id,
        encryption.encrypt(json),
        now.strftime(DATETIME_FORMAT)
    )
    assert Notification.query.count() == 1
    assert not deliver_sms.called
    assert not retry.called


def test_persist_letter_saves_letter_to_database(sample_letter_job, mocker):

    mocker.patch('app.celery.tasks.create_random_identifier', return_value="this-is-random-in-real-life")

    personalisation = {
        'addressline1': 'Foo',
        'addressline2': 'Bar',
        'addressline3': 'Baz',
        'addressline4': 'Wibble',
        'addressline5': 'Wobble',
        'addressline6': 'Wubble',
        'postcode': 'Flob',
    }
    notification_json = _notification_json(
        template=sample_letter_job.template,
        to='Foo',
        personalisation=personalisation,
        job_id=sample_letter_job.id,
        row_number=1
    )
    notification_id = uuid.uuid4()
    created_at = datetime.utcnow()

    persist_letter(
        sample_letter_job.service_id,
        notification_id,
        encryption.encrypt(notification_json),
        created_at
    )

    notification_db = Notification.query.one()
    assert notification_db.id == notification_id
    assert notification_db.to == 'Foo'
    assert notification_db.job_id == sample_letter_job.id
    assert notification_db.template_id == sample_letter_job.template.id
    assert notification_db.template_version == sample_letter_job.template.version
    assert notification_db.status == 'created'
    assert notification_db.created_at == created_at
    assert notification_db.notification_type == 'letter'
    assert notification_db.sent_at is None
    assert notification_db.sent_by is None
    assert notification_db.personalisation == personalisation
    assert notification_db.reference == "this-is-random-in-real-life"


def test_should_cancel_job_if_service_is_inactive(sample_service,
                                                  sample_job,
                                                  mocker):
    sample_service.active = False

    mocker.patch('app.celery.tasks.s3.get_job_from_s3')
    mocker.patch('app.celery.tasks.process_row')
    mock_dvla_file_task = mocker.patch('app.celery.tasks.build_dvla_file')

    process_job(sample_job.id)

    job = jobs_dao.dao_get_job_by_id(sample_job.id)
    assert job.job_status == 'cancelled'
    s3.get_job_from_s3.assert_not_called()
    tasks.process_row.assert_not_called()
    mock_dvla_file_task.assert_not_called()


@pytest.mark.parametrize('template_type, expected_class', [
    (SMS_TYPE, SMSMessageTemplate),
    (EMAIL_TYPE, WithSubjectTemplate),
    (LETTER_TYPE, WithSubjectTemplate),
])
def test_get_template_class(template_type, expected_class):
    assert get_template_class(template_type) == expected_class


def test_build_dvla_file(sample_letter_template, mocker):
    job = create_job(template=sample_letter_template, notification_count=2)
    create_notification(template=job.template, job=job)
    create_notification(template=job.template, job=job)
    mocked_upload = mocker.patch("app.celery.tasks.s3upload")
    mocked_send_task = mocker.patch("app.celery.tasks.notify_celery.send_task")
    mocked_letter_template = mocker.patch("app.celery.tasks.LetterDVLATemplate")
    mocked_letter_template_instance = mocked_letter_template.return_value
    mocked_letter_template_instance.__str__.return_value = "dvla|string"
    build_dvla_file(job.id)

    mocked_upload.assert_called_once_with(
        filedata="dvla|string\ndvla|string\n",
        region=current_app.config['AWS_REGION'],
        bucket_name=current_app.config['DVLA_UPLOAD_BUCKET_NAME'],
        file_location="{}-dvla-job.text".format(job.id)
    )
    assert Job.query.get(job.id).job_status == 'ready to send'


def test_build_dvla_file_retries_if_all_notifications_are_not_created(sample_letter_template, mocker):
    job = create_job(template=sample_letter_template, notification_count=2, job_status='in progress')
    create_notification(template=job.template, job=job)

    mocked = mocker.patch("app.celery.tasks.s3upload")
    mocked_send_task = mocker.patch("app.celery.tasks.notify_celery.send_task")
    mocker.patch('app.celery.tasks.build_dvla_file.retry', side_effect=Retry)
    with pytest.raises(Retry):
        build_dvla_file(job.id)
    mocked.assert_not_called()

    tasks.build_dvla_file.retry.assert_called_with(queue="retry-tasks",
                                                   exc="All notifications for job {} are not persisted".format(job.id))
    assert Job.query.get(job.id).job_status == 'in progress'
    mocked_send_task.assert_not_called()


def test_create_dvla_file_contents(sample_letter_template, mocker):
    job = create_job(template=sample_letter_template, notification_count=2)
    create_notification(template=job.template, job=job, reference=1)
    create_notification(template=job.template, job=job, reference=2)
    mocked_letter_template = mocker.patch("app.celery.tasks.LetterDVLATemplate")
    mocked_letter_template_instance = mocked_letter_template.return_value
    mocked_letter_template_instance.__str__.return_value = "dvla|string"

    create_dvla_file_contents(job.id)
    calls = mocked_letter_template.call_args_list
    # Template
    assert calls[0][0][0]['subject'] == 'Template subject'
    assert calls[0][0][0]['content'] == 'Dear Sir/Madam, Hello. Yours Truly, The Government.'

    # Personalisation
    assert not calls[0][0][1]
    assert not calls[1][0][1]

    # Named arguments
    assert calls[1][1]['contact_block'] == 'London,\nSW1A 1AA'
    assert calls[0][1]['notification_reference'] == '1'
    assert calls[1][1]['notification_reference'] == '2'
    assert calls[1][1]['org_id'] == '001'


@freeze_time("2017-03-23 11:09:00.061258")
def test_dvla_letter_template(sample_letter_notification):
    t = {"content": sample_letter_notification.template.content,
         "subject": sample_letter_notification.template.subject}
    letter = LetterDVLATemplate(t, sample_letter_notification.personalisation, "random-string")
    assert str(letter) == "140|500|001||random-string|||||||||||||A1||A2|A3|A4|A5|A6|A_POST|||||||||23 March 2017<cr><cr><h1>Template subject<normal><cr><cr>Dear Sir/Madam, Hello. Yours Truly, The Government.<cr><cr>"  # noqa


def test_update_job_to_sent_to_dvla(sample_letter_template, sample_letter_job):
    create_notification(template=sample_letter_template, job=sample_letter_job)
    create_notification(template=sample_letter_template, job=sample_letter_job)
    update_job_to_sent_to_dvla(job_id=sample_letter_job.id)

    updated_notifications = Notification.query.all()
    assert [(n.status == 'sending', n.sent_by == 'dvla') for n in updated_notifications]

    assert 'sent to dvla' == Job.query.filter_by(id=sample_letter_job.id).one().job_status


def test_update_dvla_job_to_error(sample_letter_template, sample_letter_job):
    create_notification(template=sample_letter_template, job=sample_letter_job)
    create_notification(template=sample_letter_template, job=sample_letter_job)
    update_dvla_job_to_error(job_id=sample_letter_job.id)

    updated_notifications = Notification.query.all()
    for n in updated_notifications:
        assert n.status == 'created'
        assert not n.sent_by

    assert 'error' == Job.query.filter_by(id=sample_letter_job.id).one().job_status


def test_update_letter_notifications_statuses_raises_for_invalid_format(notify_api, mocker):
    invalid_file = 'ref-foo|Sent|1|Unsorted\nref-bar|Sent|2'
    mocker.patch('app.celery.tasks.s3.get_s3_file', return_value=invalid_file)

    with pytest.raises(TypeError):
        update_letter_notifications_statuses(filename='foo.txt')


def test_update_letter_notifications_statuses_calls_with_correct_bucket_location(notify_api, mocker):
    s3_mock = mocker.patch('app.celery.tasks.s3.get_s3_object')

    with set_config(notify_api, 'NOTIFY_EMAIL_DOMAIN', 'foo.bar'):
        update_letter_notifications_statuses(filename='foo.txt')
        s3_mock.assert_called_with('{}-ftp'.format(current_app.config['NOTIFY_EMAIL_DOMAIN']), 'foo.txt')


def test_update_letter_notifications_statuses_builds_updates_from_content(notify_api, mocker):
    valid_file = 'ref-foo|Sent|1|Unsorted\nref-bar|Sent|2|Sorted'
    mocker.patch('app.celery.tasks.s3.get_s3_file', return_value=valid_file)
    update_mock = mocker.patch('app.celery.tasks.process_updates_from_file')

    update_letter_notifications_statuses(filename='foo.txt')

    update_mock.assert_called_with('ref-foo|Sent|1|Unsorted\nref-bar|Sent|2|Sorted')


def test_update_letter_notifications_statuses_builds_updates_list(notify_api, mocker):
    valid_file = 'ref-foo|Sent|1|Unsorted\nref-bar|Sent|2|Sorted'
    updates = process_updates_from_file(valid_file)

    assert len(updates) == 2

    assert updates[0].reference == 'ref-foo'
    assert updates[0].status == 'Sent'
    assert updates[0].page_count == '1'
    assert updates[0].cost_threshold == 'Unsorted'

    assert updates[1].reference == 'ref-bar'
    assert updates[1].status == 'Sent'
    assert updates[1].page_count == '2'
    assert updates[1].cost_threshold == 'Sorted'
