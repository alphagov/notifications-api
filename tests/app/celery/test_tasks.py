import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import Mock, call

import pytest
import requests_mock
from freezegun import freeze_time
from requests import RequestException
from sqlalchemy.exc import SQLAlchemyError
from celery.exceptions import Retry
from notifications_utils.template import SMSMessageTemplate, WithSubjectTemplate
from notifications_utils.columns import Row

from app import (
    DATETIME_FORMAT,
    encryption
)
from app.celery import provider_tasks
from app.celery import tasks
from app.celery.tasks import (
    process_job,
    process_row,
    save_sms,
    save_email,
    save_letter,
    process_incomplete_job,
    process_incomplete_jobs,
    get_template_class,
    s3,
    send_inbound_sms_to_service,
    process_returned_letters_list,
)
from app.config import QueueNames
from app.dao import jobs_dao, service_email_reply_to_dao, service_sms_sender_dao
from app.models import (
    Job,
    Notification,
    NotificationHistory,
    EMAIL_TYPE,
    KEY_TYPE_NORMAL,
    JOB_STATUS_FINISHED,
    JOB_STATUS_ERROR,
    JOB_STATUS_IN_PROGRESS,
    LETTER_TYPE,
    SMS_TYPE,
)

from tests.app import load_example_csv

from tests.app.db import (
    create_inbound_sms,
    create_job,
    create_letter_contact,
    create_notification,
    create_service_inbound_api,
    create_service,
    create_template,
    create_user,
    create_reply_to_email,
    create_service_with_defined_sms_sender,
    create_notification_history
)
from tests.conftest import set_config_values


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
    assert save_sms.__wrapped__.__name__ == 'save_sms'
    assert save_email.__wrapped__.__name__ == 'save_email'
    assert save_letter.__wrapped__.__name__ == 'save_letter'


@pytest.fixture
def email_job_with_placeholders(notify_db, notify_db_session, sample_email_template_with_placeholders):
    return create_job(template=sample_email_template_with_placeholders)


# -------------- process_job tests -------------- #


def test_should_process_sms_job(sample_job, mocker):
    mocker.patch('app.celery.tasks.s3.get_job_and_metadata_from_s3',
                 return_value=(load_example_csv('sms'), {'sender_id': None}))
    mocker.patch('app.celery.tasks.save_sms.apply_async')
    mocker.patch('app.encryption.encrypt', return_value="something_encrypted")
    mocker.patch('app.celery.tasks.create_uuid', return_value="uuid")

    process_job(sample_job.id)
    s3.get_job_and_metadata_from_s3.assert_called_once_with(
        service_id=str(sample_job.service.id),
        job_id=str(sample_job.id)
    )
    assert encryption.encrypt.call_args[0][0]['to'] == '+441234123123'
    assert encryption.encrypt.call_args[0][0]['template'] == str(sample_job.template.id)
    assert encryption.encrypt.call_args[0][0]['template_version'] == sample_job.template.version
    assert encryption.encrypt.call_args[0][0]['personalisation'] == {'phonenumber': '+441234123123'}
    assert encryption.encrypt.call_args[0][0]['row_number'] == 0
    tasks.save_sms.apply_async.assert_called_once_with(
        (str(sample_job.service_id),
         "uuid",
         "something_encrypted"),
        {},
        queue="database-tasks"
    )
    job = jobs_dao.dao_get_job_by_id(sample_job.id)
    assert job.job_status == 'finished'


def test_should_process_sms_job_with_sender_id(sample_job, mocker, fake_uuid):
    mocker.patch('app.celery.tasks.s3.get_job_and_metadata_from_s3',
                 return_value=(load_example_csv('sms'), {'sender_id': fake_uuid}))
    mocker.patch('app.celery.tasks.save_sms.apply_async')
    mocker.patch('app.encryption.encrypt', return_value="something_encrypted")
    mocker.patch('app.celery.tasks.create_uuid', return_value="uuid")

    process_job(sample_job.id, sender_id=fake_uuid)

    tasks.save_sms.apply_async.assert_called_once_with(
        (str(sample_job.service_id),
         "uuid",
         "something_encrypted"),
        {'sender_id': fake_uuid},
        queue="database-tasks"
    )


@freeze_time("2016-01-01 11:09:00.061258")
def test_should_not_process_sms_job_if_would_exceed_send_limits(
    notify_db_session, mocker
):
    service = create_service(message_limit=9)
    template = create_template(service=service)
    job = create_job(template=template, notification_count=10, original_file_name='multiple_sms.csv')
    mocker.patch('app.celery.tasks.s3.get_job_and_metadata_from_s3',
                 return_value=(load_example_csv('multiple_sms'), {'sender_id': None}))
    mocker.patch('app.celery.tasks.process_row')

    process_job(job.id)

    job = jobs_dao.dao_get_job_by_id(job.id)
    assert job.job_status == 'sending limits exceeded'
    assert s3.get_job_and_metadata_from_s3.called is False
    assert tasks.process_row.called is False


def test_should_not_process_sms_job_if_would_exceed_send_limits_inc_today(
    notify_db_session, mocker
):
    service = create_service(message_limit=1)
    template = create_template(service=service)
    job = create_job(template=template)

    create_notification(template=template, job=job)

    mocker.patch('app.celery.tasks.s3.get_job_and_metadata_from_s3',
                 return_value=(load_example_csv('sms'), {'sender_id': None}))
    mocker.patch('app.celery.tasks.process_row')

    process_job(job.id)

    job = jobs_dao.dao_get_job_by_id(job.id)
    assert job.job_status == 'sending limits exceeded'
    assert s3.get_job_and_metadata_from_s3.called is False
    assert tasks.process_row.called is False


@pytest.mark.parametrize('template_type', ['sms', 'email'])
def test_should_not_process_email_job_if_would_exceed_send_limits_inc_today(notify_db_session, template_type, mocker):
    service = create_service(message_limit=1)
    template = create_template(service=service, template_type=template_type)
    job = create_job(template=template)

    create_notification(template=template, job=job)

    mocker.patch('app.celery.tasks.s3.get_job_and_metadata_from_s3')
    mocker.patch('app.celery.tasks.process_row')

    process_job(job.id)

    job = jobs_dao.dao_get_job_by_id(job.id)
    assert job.job_status == 'sending limits exceeded'
    assert s3.get_job_and_metadata_from_s3.called is False
    assert tasks.process_row.called is False


def test_should_not_process_job_if_already_pending(sample_template, mocker):
    job = create_job(template=sample_template, job_status='scheduled')

    mocker.patch('app.celery.tasks.s3.get_job_and_metadata_from_s3')
    mocker.patch('app.celery.tasks.process_row')

    process_job(job.id)

    assert s3.get_job_and_metadata_from_s3.called is False
    assert tasks.process_row.called is False


def test_should_process_email_job_if_exactly_on_send_limits(notify_db_session,
                                                            mocker):
    service = create_service(message_limit=10)
    template = create_template(service=service, template_type='email')
    job = create_job(template=template, notification_count=10)

    mocker.patch('app.celery.tasks.s3.get_job_and_metadata_from_s3',
                 return_value=(load_example_csv('multiple_email'), {"sender_id": None}))
    mocker.patch('app.celery.tasks.save_email.apply_async')
    mocker.patch('app.encryption.encrypt', return_value="something_encrypted")
    mocker.patch('app.celery.tasks.create_uuid', return_value="uuid")

    process_job(job.id)

    s3.get_job_and_metadata_from_s3.assert_called_once_with(
        service_id=str(job.service.id),
        job_id=str(job.id)
    )
    job = jobs_dao.dao_get_job_by_id(job.id)
    assert job.job_status == 'finished'
    tasks.save_email.apply_async.assert_called_with(
        (
            str(job.service_id),
            "uuid",
            "something_encrypted",
        ),
        {},
        queue="database-tasks"
    )


def test_should_not_create_save_task_for_empty_file(sample_job, mocker):
    mocker.patch('app.celery.tasks.s3.get_job_and_metadata_from_s3',
                 return_value=(load_example_csv('empty'), {"sender_id": None}))
    mocker.patch('app.celery.tasks.save_sms.apply_async')

    process_job(sample_job.id)

    s3.get_job_and_metadata_from_s3.assert_called_once_with(
        service_id=str(sample_job.service.id),
        job_id=str(sample_job.id)
    )
    job = jobs_dao.dao_get_job_by_id(sample_job.id)
    assert job.job_status == 'finished'
    assert tasks.save_sms.apply_async.called is False


def test_should_process_email_job(email_job_with_placeholders, mocker):
    email_csv = """email_address,name
    test@test.com,foo
    """
    mocker.patch('app.celery.tasks.s3.get_job_and_metadata_from_s3', return_value=(email_csv, {"sender_id": None}))
    mocker.patch('app.celery.tasks.save_email.apply_async')
    mocker.patch('app.encryption.encrypt', return_value="something_encrypted")
    mocker.patch('app.celery.tasks.create_uuid', return_value="uuid")

    process_job(email_job_with_placeholders.id)

    s3.get_job_and_metadata_from_s3.assert_called_once_with(
        service_id=str(email_job_with_placeholders.service.id),
        job_id=str(email_job_with_placeholders.id)
    )
    assert encryption.encrypt.call_args[0][0]['to'] == 'test@test.com'
    assert encryption.encrypt.call_args[0][0]['template'] == str(email_job_with_placeholders.template.id)
    assert encryption.encrypt.call_args[0][0]['template_version'] == email_job_with_placeholders.template.version
    assert encryption.encrypt.call_args[0][0]['personalisation'] == {'emailaddress': 'test@test.com', 'name': 'foo'}
    tasks.save_email.apply_async.assert_called_once_with(
        (
            str(email_job_with_placeholders.service_id),
            "uuid",
            "something_encrypted",
        ),
        {},
        queue="database-tasks"
    )
    job = jobs_dao.dao_get_job_by_id(email_job_with_placeholders.id)
    assert job.job_status == 'finished'


def test_should_process_email_job_with_sender_id(email_job_with_placeholders, mocker, fake_uuid):
    email_csv = """email_address,name
    test@test.com,foo
    """
    mocker.patch('app.celery.tasks.s3.get_job_and_metadata_from_s3', return_value=(email_csv, {"sender_id": fake_uuid}))
    mocker.patch('app.celery.tasks.save_email.apply_async')
    mocker.patch('app.encryption.encrypt', return_value="something_encrypted")
    mocker.patch('app.celery.tasks.create_uuid', return_value="uuid")

    process_job(email_job_with_placeholders.id, sender_id=fake_uuid)

    tasks.save_email.apply_async.assert_called_once_with(
        (str(email_job_with_placeholders.service_id),
         "uuid",
         "something_encrypted"),
        {'sender_id': fake_uuid},
        queue="database-tasks"
    )


@freeze_time("2016-01-01 11:09:00.061258")
def test_should_process_letter_job(sample_letter_job, mocker):
    csv = """address_line_1,address_line_2,address_line_3,address_line_4,postcode,name
    A1,A2,A3,A4,A_POST,Alice
    """
    s3_mock = mocker.patch('app.celery.tasks.s3.get_job_and_metadata_from_s3',
                           return_value=(csv, {"sender_id": None}))
    process_row_mock = mocker.patch('app.celery.tasks.process_row')
    mocker.patch('app.celery.tasks.create_uuid', return_value="uuid")

    process_job(sample_letter_job.id)

    s3_mock.assert_called_once_with(
        service_id=str(sample_letter_job.service.id),
        job_id=str(sample_letter_job.id)
    )

    row_call = process_row_mock.mock_calls[0][1]
    assert row_call[0].index == 0
    assert row_call[0].recipient == ['A1', 'A2', 'A3', 'A4', None, None, 'A_POST']
    assert row_call[0].personalisation == {
        'addressline1': 'A1',
        'addressline2': 'A2',
        'addressline3': 'A3',
        'addressline4': 'A4',
        'postcode': 'A_POST'
    }
    assert row_call[2] == sample_letter_job
    assert row_call[3] == sample_letter_job.service

    assert process_row_mock.call_count == 1

    assert sample_letter_job.job_status == 'finished'


def test_should_process_all_sms_job(sample_job_with_placeholdered_template,
                                    mocker):
    mocker.patch('app.celery.tasks.s3.get_job_and_metadata_from_s3',
                 return_value=(load_example_csv('multiple_sms'), {"sender_id": None}))
    mocker.patch('app.celery.tasks.save_sms.apply_async')
    mocker.patch('app.encryption.encrypt', return_value="something_encrypted")
    mocker.patch('app.celery.tasks.create_uuid', return_value="uuid")

    process_job(sample_job_with_placeholdered_template.id)

    s3.get_job_and_metadata_from_s3.assert_called_once_with(
        service_id=str(sample_job_with_placeholdered_template.service.id),
        job_id=str(sample_job_with_placeholdered_template.id)
    )
    assert encryption.encrypt.call_args[0][0]['to'] == '+441234123120'
    assert encryption.encrypt.call_args[0][0]['template'] == str(sample_job_with_placeholdered_template.template.id)
    assert encryption.encrypt.call_args[0][0][
               'template_version'] == sample_job_with_placeholdered_template.template.version  # noqa
    assert encryption.encrypt.call_args[0][0]['personalisation'] == {'phonenumber': '+441234123120', 'name': 'chris'}
    assert tasks.save_sms.apply_async.call_count == 10
    job = jobs_dao.dao_get_job_by_id(sample_job_with_placeholdered_template.id)
    assert job.job_status == 'finished'


# -------------- process_row tests -------------- #


@pytest.mark.parametrize('template_type, research_mode, expected_function, expected_queue', [
    (SMS_TYPE, False, 'save_sms', 'database-tasks'),
    (SMS_TYPE, True, 'save_sms', 'research-mode-tasks'),
    (EMAIL_TYPE, False, 'save_email', 'database-tasks'),
    (EMAIL_TYPE, True, 'save_email', 'research-mode-tasks'),
    (LETTER_TYPE, False, 'save_letter', 'database-tasks'),
    (LETTER_TYPE, True, 'save_letter', 'research-mode-tasks'),
])
def test_process_row_sends_letter_task(template_type, research_mode, expected_function, expected_queue, mocker):
    mocker.patch('app.celery.tasks.create_uuid', return_value='noti_uuid')
    task_mock = mocker.patch('app.celery.tasks.{}.apply_async'.format(expected_function))
    encrypt_mock = mocker.patch('app.celery.tasks.encryption.encrypt')
    template = Mock(id='template_id', template_type=template_type)
    job = Mock(id='job_id', template_version='temp_vers')
    service = Mock(id='service_id', research_mode=research_mode)

    process_row(
        Row(
            {'foo': 'bar', 'to': 'recip'},
            index='row_num',
            error_fn=lambda k, v: None,
            recipient_column_headers=['to'],
            placeholders={'foo'},
            template=template,
        ),
        template,
        job,
        service,
    )

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
        ),
        {},
        queue=expected_queue
    )


def test_process_row_when_sender_id_is_provided(mocker, fake_uuid):
    mocker.patch('app.celery.tasks.create_uuid', return_value='noti_uuid')
    task_mock = mocker.patch('app.celery.tasks.save_sms.apply_async')
    encrypt_mock = mocker.patch('app.celery.tasks.encryption.encrypt')
    template = Mock(id='template_id', template_type=SMS_TYPE)
    job = Mock(id='job_id', template_version='temp_vers')
    service = Mock(id='service_id', research_mode=False)

    process_row(
        Row(
            {'foo': 'bar', 'to': 'recip'},
            index='row_num',
            error_fn=lambda k, v: None,
            recipient_column_headers=['to'],
            placeholders={'foo'},
            template=template,
        ),
        template,
        job,
        service,
        sender_id=fake_uuid
    )

    task_mock.assert_called_once_with(
        (
            'service_id',
            'noti_uuid',
            # encrypted data
            encrypt_mock.return_value,
        ),
        {'sender_id': fake_uuid},
        queue='database-tasks'
    )
# -------- save_sms and save_email tests -------- #


def test_should_send_template_to_correct_sms_task_and_persist(sample_template_with_placeholders, mocker):
    notification = _notification_json(sample_template_with_placeholders,
                                      to="+447234123123", personalisation={"name": "Jo"})

    mocked_deliver_sms = mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')

    save_sms(
        sample_template_with_placeholders.service_id,
        uuid.uuid4(),
        encryption.encrypt(notification),
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
        queue="send-sms-tasks"
    )


def test_should_put_save_sms_task_in_research_mode_queue_if_research_mode_service(notify_db, notify_db_session, mocker):
    service = create_service(research_mode=True, )

    template = create_template(service=service)

    notification = _notification_json(template, to="+447234123123")

    mocked_deliver_sms = mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')

    notification_id = uuid.uuid4()

    save_sms(
        template.service_id,
        notification_id,
        encryption.encrypt(notification),
    )
    persisted_notification = Notification.query.one()
    provider_tasks.deliver_sms.apply_async.assert_called_once_with(
        [str(persisted_notification.id)],
        queue="research-mode-tasks"
    )
    assert mocked_deliver_sms.called


def test_should_save_sms_if_restricted_service_and_valid_number(notify_db_session, mocker):
    user = create_user(mobile_number="07700 900890")
    service = create_service(user=user, restricted=True)
    template = create_template(service=service)
    notification = _notification_json(template, "+447700900890")  # The user’s own number, but in a different format

    mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')

    notification_id = uuid.uuid4()
    encrypt_notification = encryption.encrypt(notification)
    save_sms(
        service.id,
        notification_id,
        encrypt_notification,
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
        queue="send-sms-tasks"
    )


def test_save_email_should_save_default_email_reply_to_text_on_notification(notify_db_session, mocker):
    service = create_service()
    create_reply_to_email(service=service, email_address='reply_to@digital.gov.uk', is_default=True)
    template = create_template(service=service, template_type='email', subject='Hello')

    notification = _notification_json(template, to="test@example.com")
    mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')

    notification_id = uuid.uuid4()
    save_email(
        service.id,
        notification_id,
        encryption.encrypt(notification),
    )

    persisted_notification = Notification.query.one()
    assert persisted_notification.reply_to_text == 'reply_to@digital.gov.uk'


def test_save_sms_should_save_default_smm_sender_notification_reply_to_text_on(notify_db_session, mocker):
    service = create_service_with_defined_sms_sender(sms_sender_value='12345')
    template = create_template(service=service)

    notification = _notification_json(template, to="07700 900205")
    mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')

    notification_id = uuid.uuid4()
    save_sms(
        service.id,
        notification_id,
        encryption.encrypt(notification),
    )

    persisted_notification = Notification.query.one()
    assert persisted_notification.reply_to_text == '12345'


def test_should_not_save_sms_if_restricted_service_and_invalid_number(notify_db_session, mocker):
    user = create_user(mobile_number="07700 900205")
    service = create_service(user=user, restricted=True)
    template = create_template(service=service)

    notification = _notification_json(template, "07700 900849")
    mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')

    notification_id = uuid.uuid4()
    save_sms(
        service.id,
        notification_id,
        encryption.encrypt(notification),
    )
    assert provider_tasks.deliver_sms.apply_async.called is False
    assert Notification.query.count() == 0


def test_should_not_save_email_if_restricted_service_and_invalid_email_address(notify_db_session, mocker):
    user = create_user()
    service = create_service(user=user, restricted=True)
    template = create_template(service=service, template_type='email', subject='Hello')
    notification = _notification_json(template, to="test@example.com")

    notification_id = uuid.uuid4()
    save_email(
        service.id,
        notification_id,
        encryption.encrypt(notification),
    )

    assert Notification.query.count() == 0


def test_should_put_save_email_task_in_research_mode_queue_if_research_mode_service(
    notify_db_session, mocker
):
    service = create_service(research_mode=True)

    template = create_template(service=service, template_type='email')

    notification = _notification_json(template, to="test@test.com")

    mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')

    notification_id = uuid.uuid4()

    save_email(
        template.service_id,
        notification_id,
        encryption.encrypt(notification),
    )

    persisted_notification = Notification.query.one()
    provider_tasks.deliver_email.apply_async.assert_called_once_with(
        [str(persisted_notification.id)],
        queue="research-mode-tasks"
    )


def test_should_save_sms_template_to_and_persist_with_job_id(sample_job, mocker):
    notification = _notification_json(
        sample_job.template,
        to="+447234123123",
        job_id=sample_job.id,
        row_number=2)
    mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')

    notification_id = uuid.uuid4()
    now = datetime.utcnow()
    save_sms(
        sample_job.service.id,
        notification_id,
        encryption.encrypt(notification),
    )
    persisted_notification = Notification.query.one()
    assert persisted_notification.to == '+447234123123'
    assert persisted_notification.job_id == sample_job.id
    assert persisted_notification.template_id == sample_job.template.id
    assert persisted_notification.status == 'created'
    assert not persisted_notification.sent_at
    assert persisted_notification.created_at >= now
    assert not persisted_notification.sent_by
    assert persisted_notification.job_row_number == 2
    assert persisted_notification.api_key_id is None
    assert persisted_notification.key_type == KEY_TYPE_NORMAL
    assert persisted_notification.notification_type == 'sms'

    provider_tasks.deliver_sms.apply_async.assert_called_once_with(
        [str(persisted_notification.id)],
        queue="send-sms-tasks"
    )


def test_should_not_save_sms_if_team_key_and_recipient_not_in_team(notify_db_session, mocker):
    assert Notification.query.count() == 0
    user = create_user(mobile_number="07700 900205")
    service = create_service(user=user, restricted=True)
    template = create_template(service=service)

    team_members = [user.mobile_number for user in service.users]
    assert "07890 300000" not in team_members

    notification = _notification_json(template, "07700 900849")
    mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')

    notification_id = uuid.uuid4()
    save_sms(
        service.id,
        notification_id,
        encryption.encrypt(notification),
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
        save_email(
            sample_email_template_with_placeholders.service_id,
            notification_id,
            encryption.encrypt(notification),
        )

    persisted_notification = Notification.query.one()
    assert persisted_notification.to == 'my_email@my_email.com'
    assert persisted_notification.template_id == sample_email_template_with_placeholders.id
    assert persisted_notification.template_version == sample_email_template_with_placeholders.version
    assert persisted_notification.created_at >= now
    assert not persisted_notification.sent_at
    assert persisted_notification.status == 'created'
    assert not persisted_notification.sent_by
    assert persisted_notification.job_row_number == 1
    assert persisted_notification.personalisation == {'name': 'Jo'}
    assert persisted_notification._personalisation == encryption.encrypt({"name": "Jo"})
    assert persisted_notification.api_key_id is None
    assert persisted_notification.key_type == KEY_TYPE_NORMAL
    assert persisted_notification.notification_type == 'email'

    provider_tasks.deliver_email.apply_async.assert_called_once_with(
        [str(persisted_notification.id)], queue='send-email-tasks')


def test_save_email_should_use_template_version_from_job_not_latest(sample_email_template, mocker):
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
    save_email(
        sample_email_template.service_id,
        uuid.uuid4(),
        encryption.encrypt(notification),
    )

    persisted_notification = Notification.query.one()
    assert persisted_notification.to == 'my_email@my_email.com'
    assert persisted_notification.template_id == sample_email_template.id
    assert persisted_notification.template_version == version_on_notification
    assert persisted_notification.created_at >= now
    assert not persisted_notification.sent_at
    assert persisted_notification.status == 'created'
    assert not persisted_notification.sent_by
    assert persisted_notification.notification_type == 'email'
    provider_tasks.deliver_email.apply_async.assert_called_once_with([str(persisted_notification.id)],
                                                                     queue='send-email-tasks')


def test_should_use_email_template_subject_placeholders(sample_email_template_with_placeholders, mocker):
    notification = _notification_json(sample_email_template_with_placeholders,
                                      "my_email@my_email.com", {"name": "Jo"})
    mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')

    notification_id = uuid.uuid4()
    now = datetime.utcnow()
    save_email(
        sample_email_template_with_placeholders.service_id,
        notification_id,
        encryption.encrypt(notification),
    )
    persisted_notification = Notification.query.one()
    assert persisted_notification.to == 'my_email@my_email.com'
    assert persisted_notification.template_id == sample_email_template_with_placeholders.id
    assert persisted_notification.status == 'created'
    assert persisted_notification.created_at >= now
    assert not persisted_notification.sent_by
    assert persisted_notification.personalisation == {"name": "Jo"}
    assert not persisted_notification.reference
    assert persisted_notification.notification_type == 'email'
    provider_tasks.deliver_email.apply_async.assert_called_once_with(
        [str(persisted_notification.id)], queue='send-email-tasks'
    )


def test_save_email_uses_the_reply_to_text_when_provided(sample_email_template, mocker):
    notification = _notification_json(sample_email_template, "my_email@my_email.com")
    mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')

    service = sample_email_template.service
    notification_id = uuid.uuid4()
    service_email_reply_to_dao.add_reply_to_email_address_for_service(service.id, 'default@example.com', True)
    other_email_reply_to = service_email_reply_to_dao.add_reply_to_email_address_for_service(
        service.id, 'other@example.com', False)

    save_email(
        sample_email_template.service_id,
        notification_id,
        encryption.encrypt(notification),
        sender_id=other_email_reply_to.id,
    )
    persisted_notification = Notification.query.one()
    assert persisted_notification.notification_type == 'email'
    assert persisted_notification.reply_to_text == 'other@example.com'


def test_save_email_uses_the_default_reply_to_text_if_sender_id_is_none(sample_email_template, mocker):
    notification = _notification_json(sample_email_template, "my_email@my_email.com")
    mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')

    service = sample_email_template.service
    notification_id = uuid.uuid4()
    service_email_reply_to_dao.add_reply_to_email_address_for_service(service.id, 'default@example.com', True)

    save_email(
        sample_email_template.service_id,
        notification_id,
        encryption.encrypt(notification),
        sender_id=None,
    )
    persisted_notification = Notification.query.one()
    assert persisted_notification.notification_type == 'email'
    assert persisted_notification.reply_to_text == 'default@example.com'


def test_should_use_email_template_and_persist_without_personalisation(sample_email_template, mocker):
    notification = _notification_json(sample_email_template, "my_email@my_email.com")
    mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')

    notification_id = uuid.uuid4()

    now = datetime.utcnow()
    save_email(
        sample_email_template.service_id,
        notification_id,
        encryption.encrypt(notification),
    )
    persisted_notification = Notification.query.one()
    assert persisted_notification.to == 'my_email@my_email.com'
    assert persisted_notification.template_id == sample_email_template.id
    assert persisted_notification.created_at >= now
    assert not persisted_notification.sent_at
    assert persisted_notification.status == 'created'
    assert not persisted_notification.sent_by
    assert not persisted_notification.personalisation
    assert not persisted_notification.reference
    assert persisted_notification.notification_type == 'email'
    provider_tasks.deliver_email.apply_async.assert_called_once_with([str(persisted_notification.id)],
                                                                     queue='send-email-tasks')


def test_save_sms_should_go_to_retry_queue_if_database_errors(sample_template, mocker):
    notification = _notification_json(sample_template, "+447234123123")

    expected_exception = SQLAlchemyError()

    mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')
    mocker.patch('app.celery.tasks.save_sms.retry', side_effect=Retry)
    mocker.patch('app.notifications.process_notifications.dao_create_notification', side_effect=expected_exception)

    notification_id = uuid.uuid4()

    with pytest.raises(Retry):
        save_sms(
            sample_template.service_id,
            notification_id,
            encryption.encrypt(notification),
        )
    assert provider_tasks.deliver_sms.apply_async.called is False
    tasks.save_sms.retry.assert_called_with(exc=expected_exception, queue="retry-tasks")

    assert Notification.query.count() == 0


def test_save_email_should_go_to_retry_queue_if_database_errors(sample_email_template, mocker):
    notification = _notification_json(sample_email_template, "test@example.gov.uk")

    expected_exception = SQLAlchemyError()

    mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    mocker.patch('app.celery.tasks.save_email.retry', side_effect=Retry)
    mocker.patch('app.notifications.process_notifications.dao_create_notification', side_effect=expected_exception)

    notification_id = uuid.uuid4()

    with pytest.raises(Retry):
        save_email(
            sample_email_template.service_id,
            notification_id,
            encryption.encrypt(notification),
        )
    assert not provider_tasks.deliver_email.apply_async.called
    tasks.save_email.retry.assert_called_with(exc=expected_exception, queue="retry-tasks")

    assert Notification.query.count() == 0


def test_save_email_does_not_send_duplicate_and_does_not_put_in_retry_queue(sample_notification, mocker):
    json = _notification_json(sample_notification.template, sample_notification.to, job_id=uuid.uuid4(), row_number=1)
    deliver_email = mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    retry = mocker.patch('app.celery.tasks.save_email.retry', side_effect=Exception())

    notification_id = sample_notification.id

    save_email(
        sample_notification.service_id,
        notification_id,
        encryption.encrypt(json),
    )
    assert Notification.query.count() == 1
    assert not deliver_email.called
    assert not retry.called


def test_save_sms_does_not_send_duplicate_and_does_not_put_in_retry_queue(sample_notification, mocker):
    json = _notification_json(sample_notification.template, sample_notification.to, job_id=uuid.uuid4(), row_number=1)
    deliver_sms = mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')
    retry = mocker.patch('app.celery.tasks.save_sms.retry', side_effect=Exception())

    notification_id = sample_notification.id

    save_sms(
        sample_notification.service_id,
        notification_id,
        encryption.encrypt(json),
    )
    assert Notification.query.count() == 1
    assert not deliver_sms.called
    assert not retry.called


def test_save_letter_saves_letter_to_database(mocker, notify_db_session):
    service = create_service()
    contact_block = create_letter_contact(service=service, contact_block="Address contact", is_default=True)
    template = create_template(service=service, template_type=LETTER_TYPE, reply_to=contact_block.id)
    job = create_job(template=template)

    mocker.patch('app.celery.tasks.create_random_identifier', return_value="this-is-random-in-real-life")
    mocker.patch('app.celery.tasks.letters_pdf_tasks.create_letters_pdf.apply_async')

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
        template=job.template,
        to='Foo',
        personalisation=personalisation,
        job_id=job.id,
        row_number=1
    )
    notification_id = uuid.uuid4()
    created_at = datetime.utcnow()

    save_letter(
        job.service_id,
        notification_id,
        encryption.encrypt(notification_json),
    )

    notification_db = Notification.query.one()
    assert notification_db.id == notification_id
    assert notification_db.to == 'Foo'
    assert notification_db.job_id == job.id
    assert notification_db.template_id == job.template.id
    assert notification_db.template_version == job.template.version
    assert notification_db.status == 'created'
    assert notification_db.created_at >= created_at
    assert notification_db.notification_type == 'letter'
    assert notification_db.sent_at is None
    assert notification_db.sent_by is None
    assert notification_db.personalisation == personalisation
    assert notification_db.reference == "this-is-random-in-real-life"
    assert notification_db.reply_to_text == contact_block.contact_block


@pytest.mark.parametrize('postage', ['first', 'second'])
def test_save_letter_saves_letter_to_database_with_correct_postage(mocker, notify_db_session, postage):
    service = create_service(service_permissions=[LETTER_TYPE])
    template = create_template(service=service, template_type=LETTER_TYPE, postage=postage)
    letter_job = create_job(template=template)

    mocker.patch('app.celery.tasks.letters_pdf_tasks.create_letters_pdf.apply_async')
    notification_json = _notification_json(
        template=letter_job.template,
        to='Foo',
        personalisation={'addressline1': 'Foo', 'addressline2': 'Bar', 'postcode': 'Flob'},
        job_id=letter_job.id,
        row_number=1
    )
    notification_id = uuid.uuid4()
    save_letter(
        letter_job.service_id,
        notification_id,
        encryption.encrypt(notification_json),
    )

    notification_db = Notification.query.one()
    assert notification_db.id == notification_id
    assert notification_db.postage == postage


def test_save_letter_saves_letter_to_database_right_reply_to(mocker, notify_db_session):
    service = create_service()
    create_letter_contact(service=service, contact_block="Address contact", is_default=True)
    template = create_template(service=service, template_type=LETTER_TYPE, reply_to=None)
    job = create_job(template=template)

    mocker.patch('app.celery.tasks.create_random_identifier', return_value="this-is-random-in-real-life")
    mocker.patch('app.celery.tasks.letters_pdf_tasks.create_letters_pdf.apply_async')

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
        template=job.template,
        to='Foo',
        personalisation=personalisation,
        job_id=job.id,
        row_number=1
    )
    notification_id = uuid.uuid4()
    created_at = datetime.utcnow()

    save_letter(
        job.service_id,
        notification_id,
        encryption.encrypt(notification_json),
    )

    notification_db = Notification.query.one()
    assert notification_db.id == notification_id
    assert notification_db.to == 'Foo'
    assert notification_db.job_id == job.id
    assert notification_db.template_id == job.template.id
    assert notification_db.template_version == job.template.version
    assert notification_db.status == 'created'
    assert notification_db.created_at >= created_at
    assert notification_db.notification_type == 'letter'
    assert notification_db.sent_at is None
    assert notification_db.sent_by is None
    assert notification_db.personalisation == personalisation
    assert notification_db.reference == "this-is-random-in-real-life"
    assert not notification_db.reply_to_text


def test_save_letter_uses_template_reply_to_text(mocker, notify_db_session):
    service = create_service()
    create_letter_contact(service=service, contact_block="Address contact", is_default=True)
    template_contact = create_letter_contact(
        service=service,
        contact_block="Template address contact",
        is_default=False
    )
    template = create_template(
        service=service,
        template_type=LETTER_TYPE,
        reply_to=template_contact.id
    )

    job = create_job(template=template)

    mocker.patch('app.celery.tasks.create_random_identifier', return_value="this-is-random-in-real-life")
    mocker.patch('app.celery.tasks.letters_pdf_tasks.create_letters_pdf.apply_async')

    personalisation = {
        'addressline1': 'Foo',
        'addressline2': 'Bar',
        'postcode': 'Flob',
    }
    notification_json = _notification_json(
        template=job.template,
        to='Foo',
        personalisation=personalisation,
        job_id=job.id,
        row_number=1
    )

    save_letter(
        job.service_id,
        uuid.uuid4(),
        encryption.encrypt(notification_json),
    )

    notification_db = Notification.query.one()
    assert notification_db.reply_to_text == "Template address contact"


def test_save_sms_uses_sms_sender_reply_to_text(mocker, notify_db_session):
    service = create_service_with_defined_sms_sender(sms_sender_value='07123123123')
    template = create_template(service=service)

    notification = _notification_json(template, to="07700 900205")
    mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')

    notification_id = uuid.uuid4()
    save_sms(
        service.id,
        notification_id,
        encryption.encrypt(notification),
    )

    persisted_notification = Notification.query.one()
    assert persisted_notification.reply_to_text == '447123123123'


def test_save_sms_uses_non_default_sms_sender_reply_to_text_if_provided(mocker, notify_db_session):
    service = create_service_with_defined_sms_sender(sms_sender_value='07123123123')
    template = create_template(service=service)
    new_sender = service_sms_sender_dao.dao_add_sms_sender_for_service(service.id, 'new-sender', False)

    notification = _notification_json(template, to="07700 900205")
    mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')

    notification_id = uuid.uuid4()
    save_sms(
        service.id,
        notification_id,
        encryption.encrypt(notification),
        sender_id=new_sender.id,
    )

    persisted_notification = Notification.query.one()
    assert persisted_notification.reply_to_text == 'new-sender'


@pytest.mark.parametrize('env', ['staging', 'live'])
def test_save_letter_sets_delivered_letters_as_pdf_permission_in_research_mode_in_staging_live(
        notify_api, mocker, notify_db_session, sample_letter_job, env):
    sample_letter_job.service.research_mode = True
    sample_reference = "this-is-random-in-real-life"
    mock_create_fake_letter_response_file = mocker.patch(
        'app.celery.research_mode_tasks.create_fake_letter_response_file.apply_async')
    mocker.patch('app.celery.tasks.create_random_identifier', return_value=sample_reference)

    personalisation = {
        'addressline1': 'Foo',
        'addressline2': 'Bar',
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

    with set_config_values(notify_api, {
        'NOTIFY_ENVIRONMENT': env
    }):
        save_letter(
            sample_letter_job.service_id,
            notification_id,
            encryption.encrypt(notification_json),
        )

    notification = Notification.query.filter(Notification.id == notification_id).one()
    assert notification.status == 'delivered'
    assert not mock_create_fake_letter_response_file.called


@pytest.mark.parametrize('env', ['development', 'preview'])
def test_save_letter_calls_create_fake_response_for_letters_in_research_mode_on_development_preview(
        notify_api, mocker, notify_db_session, sample_letter_job, env):
    sample_letter_job.service.research_mode = True
    sample_reference = "this-is-random-in-real-life"
    mock_create_fake_letter_response_file = mocker.patch(
        'app.celery.research_mode_tasks.create_fake_letter_response_file.apply_async')
    mocker.patch('app.celery.tasks.create_random_identifier', return_value=sample_reference)

    personalisation = {
        'addressline1': 'Foo',
        'addressline2': 'Bar',
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

    with set_config_values(notify_api, {
        'NOTIFY_ENVIRONMENT': env
    }):
        save_letter(
            sample_letter_job.service_id,
            notification_id,
            encryption.encrypt(notification_json),
        )

    mock_create_fake_letter_response_file.assert_called_once_with(
        (sample_reference,),
        queue=QueueNames.RESEARCH_MODE
    )


def test_save_letter_calls_create_letters_pdf_task_not_in_research(
        mocker, notify_db_session, sample_letter_job):
    mock_create_letters_pdf = mocker.patch('app.celery.letters_pdf_tasks.create_letters_pdf.apply_async')

    personalisation = {
        'addressline1': 'Foo',
        'addressline2': 'Bar',
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

    save_letter(
        sample_letter_job.service_id,
        notification_id,
        encryption.encrypt(notification_json),
    )

    assert mock_create_letters_pdf.called
    mock_create_letters_pdf.assert_called_once_with(
        [str(notification_id)],
        queue=QueueNames.CREATE_LETTERS_PDF
    )


def test_should_cancel_job_if_service_is_inactive(sample_service,
                                                  sample_job,
                                                  mocker):
    sample_service.active = False

    mocker.patch('app.celery.tasks.s3.get_job_from_s3')
    mocker.patch('app.celery.tasks.process_row')

    process_job(sample_job.id)

    job = jobs_dao.dao_get_job_by_id(sample_job.id)
    assert job.job_status == 'cancelled'
    s3.get_job_from_s3.assert_not_called()
    tasks.process_row.assert_not_called()


@pytest.mark.parametrize('template_type, expected_class', [
    (SMS_TYPE, SMSMessageTemplate),
    (EMAIL_TYPE, WithSubjectTemplate),
    (LETTER_TYPE, WithSubjectTemplate),
])
def test_get_template_class(template_type, expected_class):
    assert get_template_class(template_type) == expected_class


def test_send_inbound_sms_to_service_post_https_request_to_service(notify_api, sample_service):
    inbound_api = create_service_inbound_api(service=sample_service, url="https://some.service.gov.uk/",
                                             bearer_token="something_unique")
    inbound_sms = create_inbound_sms(service=sample_service, notify_number="0751421", user_number="447700900111",
                                     provider_date=datetime(2017, 6, 20), content="Here is some content")
    data = {
        "id": str(inbound_sms.id),
        "source_number": inbound_sms.user_number,
        "destination_number": inbound_sms.notify_number,
        "message": inbound_sms.content,
        "date_received": inbound_sms.provider_date.strftime(DATETIME_FORMAT)
    }

    with requests_mock.Mocker() as request_mock:
        request_mock.post(inbound_api.url,
                          json={},
                          status_code=200)
        send_inbound_sms_to_service(inbound_sms.id, inbound_sms.service_id)
    assert request_mock.call_count == 1
    assert request_mock.request_history[0].url == inbound_api.url
    assert request_mock.request_history[0].method == 'POST'
    assert request_mock.request_history[0].text == json.dumps(data)
    assert request_mock.request_history[0].headers["Content-type"] == "application/json"
    assert request_mock.request_history[0].headers["Authorization"] == "Bearer {}".format(inbound_api.bearer_token)


def test_send_inbound_sms_to_service_does_not_send_request_when_inbound_sms_does_not_exist(notify_api, sample_service):
    inbound_api = create_service_inbound_api(service=sample_service)
    with requests_mock.Mocker() as request_mock:
        request_mock.post(inbound_api.url,
                          json={},
                          status_code=200)
        with pytest.raises(SQLAlchemyError):
            send_inbound_sms_to_service(inbound_sms_id=uuid.uuid4(), service_id=sample_service.id)

    assert request_mock.call_count == 0


def test_send_inbound_sms_to_service_does_not_sent_request_when_inbound_api_does_not_exist(
        notify_api, sample_service, mocker):
    inbound_sms = create_inbound_sms(service=sample_service, notify_number="0751421", user_number="447700900111",
                                     provider_date=datetime(2017, 6, 20), content="Here is some content")
    mocked = mocker.patch("requests.request")
    send_inbound_sms_to_service(inbound_sms.id, inbound_sms.service_id)

    mocked.call_count == 0


def test_send_inbound_sms_to_service_retries_if_request_returns_500(notify_api, sample_service, mocker):
    inbound_api = create_service_inbound_api(service=sample_service, url="https://some.service.gov.uk/",
                                             bearer_token="something_unique")
    inbound_sms = create_inbound_sms(service=sample_service, notify_number="0751421", user_number="447700900111",
                                     provider_date=datetime(2017, 6, 20), content="Here is some content")

    mocked = mocker.patch('app.celery.tasks.send_inbound_sms_to_service.retry')
    with requests_mock.Mocker() as request_mock:
        request_mock.post(inbound_api.url,
                          json={},
                          status_code=500)
        send_inbound_sms_to_service(inbound_sms.id, inbound_sms.service_id)

    assert mocked.call_count == 1
    assert mocked.call_args[1]['queue'] == 'retry-tasks'


def test_send_inbound_sms_to_service_retries_if_request_throws_unknown(notify_api, sample_service, mocker):
    create_service_inbound_api(
        service=sample_service,
        url="https://some.service.gov.uk/",
        bearer_token="something_unique")
    inbound_sms = create_inbound_sms(service=sample_service, notify_number="0751421", user_number="447700900111",
                                     provider_date=datetime(2017, 6, 20), content="Here is some content")

    mocked = mocker.patch('app.celery.tasks.send_inbound_sms_to_service.retry')
    mocker.patch("app.celery.tasks.request", side_effect=RequestException())

    send_inbound_sms_to_service(inbound_sms.id, inbound_sms.service_id)

    assert mocked.call_count == 1
    assert mocked.call_args[1]['queue'] == 'retry-tasks'


def test_send_inbound_sms_to_service_does_not_retries_if_request_returns_404(notify_api, sample_service, mocker):
    inbound_api = create_service_inbound_api(service=sample_service, url="https://some.service.gov.uk/",
                                             bearer_token="something_unique")
    inbound_sms = create_inbound_sms(service=sample_service, notify_number="0751421", user_number="447700900111",
                                     provider_date=datetime(2017, 6, 20), content="Here is some content")

    mocked = mocker.patch('app.celery.tasks.send_inbound_sms_to_service.retry')
    with requests_mock.Mocker() as request_mock:
        request_mock.post(inbound_api.url,
                          json={},
                          status_code=404)
        send_inbound_sms_to_service(inbound_sms.id, inbound_sms.service_id)

    mocked.call_count == 0


def test_process_incomplete_job_sms(mocker, sample_template):

    mocker.patch('app.celery.tasks.s3.get_job_and_metadata_from_s3',
                 return_value=(load_example_csv('multiple_sms'), {'sender_id': None}))
    save_sms = mocker.patch('app.celery.tasks.save_sms.apply_async')

    job = create_job(template=sample_template, notification_count=10,
                     created_at=datetime.utcnow() - timedelta(hours=2),
                     scheduled_for=datetime.utcnow() - timedelta(minutes=31),
                     processing_started=datetime.utcnow() - timedelta(minutes=31),
                     job_status=JOB_STATUS_ERROR)

    create_notification(sample_template, job, 0)
    create_notification(sample_template, job, 1)

    assert Notification.query.filter(Notification.job_id == job.id).count() == 2

    process_incomplete_job(str(job.id))

    completed_job = Job.query.filter(Job.id == job.id).one()

    assert completed_job.job_status == JOB_STATUS_FINISHED

    assert save_sms.call_count == 8  # There are 10 in the file and we've added two already


def test_process_incomplete_job_with_notifications_all_sent(mocker, sample_template):

    mocker.patch('app.celery.tasks.s3.get_job_and_metadata_from_s3',
                 return_value=(load_example_csv('multiple_sms'), {'sender_id': None}))
    mock_save_sms = mocker.patch('app.celery.tasks.save_sms.apply_async')

    job = create_job(template=sample_template, notification_count=10,
                     created_at=datetime.utcnow() - timedelta(hours=2),
                     scheduled_for=datetime.utcnow() - timedelta(minutes=31),
                     processing_started=datetime.utcnow() - timedelta(minutes=31),
                     job_status=JOB_STATUS_ERROR)

    create_notification(sample_template, job, 0)
    create_notification(sample_template, job, 1)
    create_notification(sample_template, job, 2)
    create_notification(sample_template, job, 3)
    create_notification(sample_template, job, 4)
    create_notification(sample_template, job, 5)
    create_notification(sample_template, job, 6)
    create_notification(sample_template, job, 7)
    create_notification(sample_template, job, 8)
    create_notification(sample_template, job, 9)

    assert Notification.query.filter(Notification.job_id == job.id).count() == 10

    process_incomplete_job(str(job.id))

    completed_job = Job.query.filter(Job.id == job.id).one()

    assert completed_job.job_status == JOB_STATUS_FINISHED

    assert mock_save_sms.call_count == 0  # There are 10 in the file and we've added 10 it should not have been called


def test_process_incomplete_jobs_sms(mocker, sample_template):

    mocker.patch('app.celery.tasks.s3.get_job_and_metadata_from_s3',
                 return_value=(load_example_csv('multiple_sms'), {'sender_id': None}))
    mock_save_sms = mocker.patch('app.celery.tasks.save_sms.apply_async')

    job = create_job(template=sample_template, notification_count=10,
                     created_at=datetime.utcnow() - timedelta(hours=2),
                     scheduled_for=datetime.utcnow() - timedelta(minutes=31),
                     processing_started=datetime.utcnow() - timedelta(minutes=31),
                     job_status=JOB_STATUS_ERROR)
    create_notification(sample_template, job, 0)
    create_notification(sample_template, job, 1)
    create_notification(sample_template, job, 2)

    assert Notification.query.filter(Notification.job_id == job.id).count() == 3

    job2 = create_job(template=sample_template, notification_count=10,
                      created_at=datetime.utcnow() - timedelta(hours=2),
                      scheduled_for=datetime.utcnow() - timedelta(minutes=31),
                      processing_started=datetime.utcnow() - timedelta(minutes=31),
                      job_status=JOB_STATUS_ERROR)

    create_notification(sample_template, job2, 0)
    create_notification(sample_template, job2, 1)
    create_notification(sample_template, job2, 2)
    create_notification(sample_template, job2, 3)
    create_notification(sample_template, job2, 4)

    assert Notification.query.filter(Notification.job_id == job2.id).count() == 5

    jobs = [job.id, job2.id]
    process_incomplete_jobs(jobs)

    completed_job = Job.query.filter(Job.id == job.id).one()
    completed_job2 = Job.query.filter(Job.id == job2.id).one()

    assert completed_job.job_status == JOB_STATUS_FINISHED

    assert completed_job2.job_status == JOB_STATUS_FINISHED

    assert mock_save_sms.call_count == 12  # There are 20 in total over 2 jobs we've added 8 already


def test_process_incomplete_jobs_no_notifications_added(mocker, sample_template):
    mocker.patch('app.celery.tasks.s3.get_job_and_metadata_from_s3',
                 return_value=(load_example_csv('multiple_sms'), {'sender_id': None}))
    mock_save_sms = mocker.patch('app.celery.tasks.save_sms.apply_async')

    job = create_job(template=sample_template, notification_count=10,
                     created_at=datetime.utcnow() - timedelta(hours=2),
                     scheduled_for=datetime.utcnow() - timedelta(minutes=31),
                     processing_started=datetime.utcnow() - timedelta(minutes=31),
                     job_status=JOB_STATUS_ERROR)

    assert Notification.query.filter(Notification.job_id == job.id).count() == 0

    process_incomplete_job(job.id)

    completed_job = Job.query.filter(Job.id == job.id).one()

    assert completed_job.job_status == JOB_STATUS_FINISHED

    assert mock_save_sms.call_count == 10  # There are 10 in the csv file


def test_process_incomplete_jobs(mocker):

    mocker.patch('app.celery.tasks.s3.get_job_and_metadata_from_s3',
                 return_value=(load_example_csv('multiple_sms'), {'sender_id': None}))
    mock_save_sms = mocker.patch('app.celery.tasks.save_sms.apply_async')

    jobs = []
    process_incomplete_jobs(jobs)

    assert mock_save_sms.call_count == 0  # There are no jobs to process so it will not have been called


def test_process_incomplete_job_no_job_in_database(mocker, fake_uuid):

    mocker.patch('app.celery.tasks.s3.get_job_and_metadata_from_s3',
                 return_value=(load_example_csv('multiple_sms'), {'sender_id': None}))
    mock_save_sms = mocker.patch('app.celery.tasks.save_sms.apply_async')

    with pytest.raises(expected_exception=Exception):
        process_incomplete_job(fake_uuid)

    assert mock_save_sms.call_count == 0  # There is no job in the db it will not have been called


def test_process_incomplete_job_email(mocker, sample_email_template):

    mocker.patch('app.celery.tasks.s3.get_job_and_metadata_from_s3',
                 return_value=(load_example_csv('multiple_email'), {'sender_id': None}))
    mock_email_saver = mocker.patch('app.celery.tasks.save_email.apply_async')

    job = create_job(template=sample_email_template, notification_count=10,
                     created_at=datetime.utcnow() - timedelta(hours=2),
                     scheduled_for=datetime.utcnow() - timedelta(minutes=31),
                     processing_started=datetime.utcnow() - timedelta(minutes=31),
                     job_status=JOB_STATUS_ERROR)

    create_notification(sample_email_template, job, 0)
    create_notification(sample_email_template, job, 1)

    assert Notification.query.filter(Notification.job_id == job.id).count() == 2

    process_incomplete_job(str(job.id))

    completed_job = Job.query.filter(Job.id == job.id).one()

    assert completed_job.job_status == JOB_STATUS_FINISHED

    assert mock_email_saver.call_count == 8  # There are 10 in the file and we've added two already


def test_process_incomplete_job_letter(mocker, sample_letter_template):
    mocker.patch('app.celery.tasks.s3.get_job_and_metadata_from_s3',
                 return_value=(load_example_csv('multiple_letter'), {'sender_id': None}))
    mock_letter_saver = mocker.patch('app.celery.tasks.save_letter.apply_async')

    job = create_job(template=sample_letter_template, notification_count=10,
                     created_at=datetime.utcnow() - timedelta(hours=2),
                     scheduled_for=datetime.utcnow() - timedelta(minutes=31),
                     processing_started=datetime.utcnow() - timedelta(minutes=31),
                     job_status=JOB_STATUS_ERROR)

    create_notification(sample_letter_template, job, 0)
    create_notification(sample_letter_template, job, 1)

    assert Notification.query.filter(Notification.job_id == job.id).count() == 2

    process_incomplete_job(str(job.id))

    assert mock_letter_saver.call_count == 8


@freeze_time('2017-01-01')
def test_process_incomplete_jobs_sets_status_to_in_progress_and_resets_processing_started_time(mocker, sample_template):
    mock_process_incomplete_job = mocker.patch('app.celery.tasks.process_incomplete_job')

    job1 = create_job(
        sample_template,
        processing_started=datetime.utcnow() - timedelta(minutes=30),
        job_status=JOB_STATUS_ERROR
    )
    job2 = create_job(
        sample_template,
        processing_started=datetime.utcnow() - timedelta(minutes=31),
        job_status=JOB_STATUS_ERROR
    )

    process_incomplete_jobs([str(job1.id), str(job2.id)])

    assert job1.job_status == JOB_STATUS_IN_PROGRESS
    assert job1.processing_started == datetime.utcnow()

    assert job2.job_status == JOB_STATUS_IN_PROGRESS
    assert job2.processing_started == datetime.utcnow()

    assert mock_process_incomplete_job.mock_calls == [call(str(job1.id)), call(str(job2.id))]


def test_process_returned_letters_list(sample_letter_template):
    create_notification(sample_letter_template, reference='ref1')
    create_notification(sample_letter_template, reference='ref2')

    process_returned_letters_list(['ref1', 'ref2', 'unknown-ref'])

    notifications = Notification.query.all()

    assert [n.status for n in notifications] == ['returned-letter', 'returned-letter']
    assert all(n.updated_at for n in notifications)


def test_process_returned_letters_list_updates_history_if_notification_is_already_purged(
        sample_letter_template
):
    create_notification_history(sample_letter_template, reference='ref1')
    create_notification_history(sample_letter_template, reference='ref2')

    process_returned_letters_list(['ref1', 'ref2', 'unknown-ref'])

    notifications = NotificationHistory.query.all()

    assert [n.status for n in notifications] == ['returned-letter', 'returned-letter']
    assert all(n.updated_at for n in notifications)
