import json
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, call

import pytest
import requests_mock
from celery.exceptions import Retry
from freezegun import freeze_time
from notifications_utils.recipients import Row
from notifications_utils.template import (
    LetterPrintTemplate,
    PlainTextEmailTemplate,
    SMSMessageTemplate,
)
from requests import RequestException
from sqlalchemy.exc import SQLAlchemyError

from app import signing
from app.celery import provider_tasks, tasks
from app.celery.tasks import (
    get_recipient_csv_and_template_and_sender_id,
    process_incomplete_job,
    process_incomplete_jobs,
    process_job,
    process_returned_letters_list,
    process_row,
    s3,
    save_api_email,
    save_api_sms,
    save_email,
    save_letter,
    save_sms,
    send_inbound_sms_to_service,
)
from app.config import QueueNames
from app.constants import (
    EMAIL_TYPE,
    JOB_STATUS_ERROR,
    JOB_STATUS_FINISHED,
    JOB_STATUS_IN_PROGRESS,
    KEY_TYPE_NORMAL,
    LETTER_TYPE,
    NOTIFICATION_CREATED,
    SMS_TYPE,
)
from app.dao import jobs_dao, service_email_reply_to_dao, service_sms_sender_dao
from app.models import Job, Notification, NotificationHistory, ReturnedLetter
from app.serialised_models import SerialisedService, SerialisedTemplate
from app.utils import DATETIME_FORMAT
from app.v2.errors import TooManyRequestsError
from tests.app import load_example_csv
from tests.app.db import (
    create_api_key,
    create_inbound_sms,
    create_job,
    create_letter_contact,
    create_notification,
    create_notification_history,
    create_reply_to_email,
    create_service,
    create_service_inbound_api,
    create_service_with_defined_sms_sender,
    create_template,
    create_user,
)


class AnyStringWith(str):
    def __eq__(self, other):
        return self in other


mmg_error = {"Error": "40", "Description": "error"}


def _notification_json(template, to, personalisation=None, job_id=None, row_number=0, client_reference=None):
    return {
        "template": str(template.id),
        "template_version": template.version,
        "to": to,
        "notification_type": template.template_type,
        "personalisation": personalisation or {},
        "job": job_id and str(job_id),
        "row_number": row_number,
        "client_reference": client_reference,
    }


def test_should_have_decorated_tasks_functions():
    assert process_job.__wrapped__.__name__ == "process_job"
    assert save_sms.__wrapped__.__name__ == "save_sms"
    assert save_email.__wrapped__.__name__ == "save_email"
    assert save_letter.__wrapped__.__name__ == "save_letter"


@pytest.fixture
def email_job_with_placeholders(notify_db_session, sample_email_template_with_placeholders):
    return create_job(template=sample_email_template_with_placeholders)


# -------------- process_job tests -------------- #


def test_should_process_sms_job(sample_job, mocker):
    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3", return_value=(load_example_csv("sms"), {"sender_id": None})
    )
    mocker.patch("app.celery.tasks.save_sms.apply_async")
    mocker.patch("app.signing.encode", return_value="something_encoded")
    mocker.patch("app.celery.tasks.create_uuid", return_value="uuid")

    process_job(sample_job.id)
    s3.get_job_and_metadata_from_s3.assert_called_once_with(
        service_id=str(sample_job.service.id), job_id=str(sample_job.id)
    )
    assert signing.encode.call_args[0][0]["to"] == "+441234123123"
    assert signing.encode.call_args[0][0]["template"] == str(sample_job.template.id)
    assert signing.encode.call_args[0][0]["template_version"] == sample_job.template.version
    assert signing.encode.call_args[0][0]["personalisation"] == {"phonenumber": "+441234123123"}
    assert signing.encode.call_args[0][0]["row_number"] == 0
    tasks.save_sms.apply_async.assert_called_once_with(
        (str(sample_job.service_id), "uuid", "something_encoded"), {}, queue="database-tasks"
    )
    job = jobs_dao.dao_get_job_by_id(sample_job.id)
    assert job.job_status == "finished"


def test_should_process_sms_job_with_sender_id(sample_job, mocker, fake_uuid):
    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=(load_example_csv("sms"), {"sender_id": fake_uuid}),
    )
    mocker.patch("app.celery.tasks.save_sms.apply_async")
    mocker.patch("app.signing.encode", return_value="something_encoded")
    mocker.patch("app.celery.tasks.create_uuid", return_value="uuid")

    process_job(sample_job.id, sender_id=fake_uuid)

    tasks.save_sms.apply_async.assert_called_once_with(
        (str(sample_job.service_id), "uuid", "something_encoded"), {"sender_id": fake_uuid}, queue="database-tasks"
    )


def test_should_not_process_job_if_already_pending(sample_template, mocker):
    job = create_job(template=sample_template, job_status="scheduled")

    mocker.patch("app.celery.tasks.s3.get_job_and_metadata_from_s3")
    mocker.patch("app.celery.tasks.process_row")

    process_job(job.id)

    assert s3.get_job_and_metadata_from_s3.called is False
    assert tasks.process_row.called is False


def test_should_not_process_if_send_limit_is_exceeded(notify_api, notify_db_session, mocker):
    service = create_service(sms_message_limit=20)
    template = create_template(service=service)
    job = create_job(template=template, notification_count=10, original_file_name="multiple_sms.csv")
    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=(load_example_csv("multiple_sms"), {"sender_id": None}),
    )
    mocker.patch("app.celery.tasks.process_row")
    mock_check_message_limit = mocker.patch(
        "app.celery.tasks.check_service_over_daily_message_limit",
        side_effect=TooManyRequestsError("total", "exceeded limit"),
    )
    process_job(job.id)

    job = jobs_dao.dao_get_job_by_id(job.id)
    assert job.job_status == "sending limits exceeded"
    assert s3.get_job_and_metadata_from_s3.called is False
    assert tasks.process_row.called is False
    assert mock_check_message_limit.call_args_list == [
        mocker.call(service, "normal", notification_type=SMS_TYPE, num_notifications=10),
    ]


def test_should_not_process_if_send_limit_is_exceeded_by_job_notification_count(notify_api, notify_db_session, mocker):
    service = create_service(sms_message_limit=9)
    template = create_template(service=service)
    job = create_job(template=template, notification_count=10, original_file_name="multiple_sms.csv")
    mock_s3 = mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=(load_example_csv("multiple_sms"), {"sender_id": None}),
    )
    mock_process_row = mocker.patch("app.celery.tasks.process_row")
    mock_check_message_limit = mocker.patch(
        "app.celery.tasks.check_service_over_daily_message_limit", side_effect=TooManyRequestsError("total", 9)
    )
    process_job(job.id)

    job = jobs_dao.dao_get_job_by_id(job.id)
    assert job.job_status == "sending limits exceeded"
    mock_s3.assert_not_called()
    mock_process_row.assert_not_called()
    assert mock_check_message_limit.call_args_list == [
        mocker.call(service, "normal", notification_type=SMS_TYPE, num_notifications=10),
    ]


def test_should_process_job_if_send_limits_are_not_exceeded(notify_api, notify_db_session, mocker):
    service = create_service(sms_message_limit=10)
    template = create_template(service=service, template_type="email")
    job = create_job(template=template, notification_count=10)

    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=(load_example_csv("multiple_email"), {"sender_id": None}),
    )
    mocker.patch("app.celery.tasks.save_email.apply_async")
    mocker.patch("app.signing.encode", return_value="something_encoded")
    mocker.patch("app.celery.tasks.create_uuid", return_value="uuid")
    mock_check_message_limit = mocker.patch(
        "app.celery.tasks.check_service_over_daily_message_limit", return_value=None
    )
    process_job(job.id)

    s3.get_job_and_metadata_from_s3.assert_called_once_with(service_id=str(job.service.id), job_id=str(job.id))
    job = jobs_dao.dao_get_job_by_id(job.id)
    assert job.job_status == "finished"
    tasks.save_email.apply_async.assert_called_with(
        (
            str(job.service_id),
            "uuid",
            "something_encoded",
        ),
        {},
        queue="database-tasks",
    )
    assert mock_check_message_limit.call_args_list == [
        mocker.call(service, "normal", notification_type=EMAIL_TYPE, num_notifications=10),
    ]


def test_should_not_create_save_task_for_empty_file(sample_job, mocker):
    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=(load_example_csv("empty"), {"sender_id": None}),
    )
    mocker.patch("app.celery.tasks.save_sms.apply_async")

    process_job(sample_job.id)

    s3.get_job_and_metadata_from_s3.assert_called_once_with(
        service_id=str(sample_job.service.id), job_id=str(sample_job.id)
    )
    job = jobs_dao.dao_get_job_by_id(sample_job.id)
    assert job.job_status == "finished"
    assert tasks.save_sms.apply_async.called is False


def test_should_process_email_job(email_job_with_placeholders, mocker):
    email_csv = """email_address,name
    test@test.com,foo
    """
    mocker.patch("app.celery.tasks.s3.get_job_and_metadata_from_s3", return_value=(email_csv, {"sender_id": None}))
    mocker.patch("app.celery.tasks.save_email.apply_async")
    mocker.patch("app.signing.encode", return_value="something_encoded")
    mocker.patch("app.celery.tasks.create_uuid", return_value="uuid")

    process_job(email_job_with_placeholders.id)

    s3.get_job_and_metadata_from_s3.assert_called_once_with(
        service_id=str(email_job_with_placeholders.service.id), job_id=str(email_job_with_placeholders.id)
    )
    assert signing.encode.call_args[0][0]["to"] == "test@test.com"
    assert signing.encode.call_args[0][0]["template"] == str(email_job_with_placeholders.template.id)
    assert signing.encode.call_args[0][0]["template_version"] == email_job_with_placeholders.template.version
    assert signing.encode.call_args[0][0]["personalisation"] == {"emailaddress": "test@test.com", "name": "foo"}
    tasks.save_email.apply_async.assert_called_once_with(
        (
            str(email_job_with_placeholders.service_id),
            "uuid",
            "something_encoded",
        ),
        {},
        queue="database-tasks",
    )
    job = jobs_dao.dao_get_job_by_id(email_job_with_placeholders.id)
    assert job.job_status == "finished"


def test_should_process_email_job_with_sender_id(email_job_with_placeholders, mocker, fake_uuid):
    email_csv = """email_address,name
    test@test.com,foo
    """
    mocker.patch("app.celery.tasks.s3.get_job_and_metadata_from_s3", return_value=(email_csv, {"sender_id": fake_uuid}))
    mocker.patch("app.celery.tasks.save_email.apply_async")
    mocker.patch("app.signing.encode", return_value="something_encoded")
    mocker.patch("app.celery.tasks.create_uuid", return_value="uuid")

    process_job(email_job_with_placeholders.id, sender_id=fake_uuid)

    tasks.save_email.apply_async.assert_called_once_with(
        (str(email_job_with_placeholders.service_id), "uuid", "something_encoded"),
        {"sender_id": fake_uuid},
        queue="database-tasks",
    )


@freeze_time("2016-01-01 11:09:00.061258")
def test_should_process_letter_job(sample_letter_job, mocker):
    csv = """address_line_1,address_line_2,address_line_3,address_line_4,postcode,name
    A1,A2,A3,A4,A_POST,Alice
    """
    s3_mock = mocker.patch("app.celery.tasks.s3.get_job_and_metadata_from_s3", return_value=(csv, {"sender_id": None}))
    process_row_mock = mocker.patch("app.celery.tasks.process_row")
    mocker.patch("app.celery.tasks.create_uuid", return_value="uuid")

    process_job(sample_letter_job.id)

    s3_mock.assert_called_once_with(service_id=str(sample_letter_job.service.id), job_id=str(sample_letter_job.id))

    row_call = process_row_mock.mock_calls[0][1]
    assert row_call[0].index == 0
    assert row_call[0].recipient == ["A1", "A2", "A3", "A4", None, None, "A_POST", None]
    assert row_call[0].personalisation == {
        "addressline1": "A1",
        "addressline2": "A2",
        "addressline3": "A3",
        "addressline4": "A4",
        "postcode": "A_POST",
    }
    assert row_call[2] == sample_letter_job
    assert row_call[3] == sample_letter_job.service

    assert process_row_mock.call_count == 1

    assert sample_letter_job.job_status == "finished"


def test_should_process_all_sms_job(sample_job_with_placeholdered_template, mocker):
    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=(load_example_csv("multiple_sms"), {"sender_id": None}),
    )
    mocker.patch("app.celery.tasks.save_sms.apply_async")
    mocker.patch("app.signing.encode", return_value="something_encoded")
    mocker.patch("app.celery.tasks.create_uuid", return_value="uuid")

    process_job(sample_job_with_placeholdered_template.id)

    s3.get_job_and_metadata_from_s3.assert_called_once_with(
        service_id=str(sample_job_with_placeholdered_template.service.id),
        job_id=str(sample_job_with_placeholdered_template.id),
    )
    assert signing.encode.call_args[0][0]["to"] == "+441234123120"
    assert signing.encode.call_args[0][0]["template"] == str(sample_job_with_placeholdered_template.template.id)
    assert (
        signing.encode.call_args[0][0]["template_version"] == sample_job_with_placeholdered_template.template.version
    )  # noqa
    assert signing.encode.call_args[0][0]["personalisation"] == {"phonenumber": "+441234123120", "name": "chris"}
    assert tasks.save_sms.apply_async.call_count == 10
    job = jobs_dao.dao_get_job_by_id(sample_job_with_placeholdered_template.id)
    assert job.job_status == "finished"


# -------------- process_row tests -------------- #


@pytest.mark.parametrize(
    "template_type, expected_function",
    [
        (SMS_TYPE, "save_sms"),
        (EMAIL_TYPE, "save_email"),
        (LETTER_TYPE, "save_letter"),
    ],
)
def test_process_row_sends_letter_task(template_type, expected_function, mocker):
    mocker.patch("app.celery.tasks.create_uuid", return_value="noti_uuid")
    task_mock = mocker.patch("app.celery.tasks.{}.apply_async".format(expected_function))
    signing_mock = mocker.patch("app.celery.tasks.signing.encode")
    template = Mock(id="template_id", template_type=template_type)
    job = Mock(id="job_id", template_version="temp_vers")
    service = Mock(id="service_id")

    process_row(
        Row(
            {"foo": "bar", "to": "recip"},
            index="row_num",
            error_fn=lambda k, v: None,
            recipient_column_headers=["to"],
            placeholders={"foo"},
            template=template,
            allow_international_letters=True,
        ),
        template,
        job,
        service,
    )

    signing_mock.assert_called_once_with(
        {
            "template": "template_id",
            "template_version": "temp_vers",
            "job": "job_id",
            "to": "recip",
            "row_number": "row_num",
            "personalisation": {"foo": "bar"},
            "client_reference": None,
        }
    )
    task_mock.assert_called_once_with(
        (
            "service_id",
            "noti_uuid",
            # encoded data
            signing_mock.return_value,
        ),
        {},
        queue="database-tasks",
    )


def test_process_row_when_sender_id_is_provided(mocker, fake_uuid):
    mocker.patch("app.celery.tasks.create_uuid", return_value="noti_uuid")
    task_mock = mocker.patch("app.celery.tasks.save_sms.apply_async")
    signing_mock = mocker.patch("app.celery.tasks.signing.encode")
    template = Mock(id="template_id", template_type=SMS_TYPE)
    job = Mock(id="job_id", template_version="temp_vers")
    service = Mock(id="service_id")

    process_row(
        Row(
            {"foo": "bar", "to": "recip"},
            index="row_num",
            error_fn=lambda k, v: None,
            recipient_column_headers=["to"],
            placeholders={"foo"},
            template=template,
            allow_international_letters=True,
        ),
        template,
        job,
        service,
        sender_id=fake_uuid,
    )

    task_mock.assert_called_once_with(
        (
            "service_id",
            "noti_uuid",
            # encoded data
            signing_mock.return_value,
        ),
        {"sender_id": fake_uuid},
        queue="database-tasks",
    )


def test_process_row_when_reference_is_provided(mocker, fake_uuid):
    mocker.patch("app.celery.tasks.create_uuid", return_value="noti_uuid")
    mocker.patch("app.celery.tasks.save_sms.apply_async")
    signing_mock = mocker.patch("app.celery.tasks.signing.encode")
    template = Mock(id="template_id", template_type=SMS_TYPE)
    job = Mock(id="job_id", template_version="temp_vers")
    service = Mock(id="service_id")

    process_row(
        Row(
            {"to": "07900100100", "name": "foo", "reference": "ab1234"},
            index=0,
            error_fn=lambda k, v: None,
            recipient_column_headers=["to"],
            placeholders={"name"},
            template=template,
            allow_international_letters=True,
        ),
        template,
        job,
        service,
        sender_id=fake_uuid,
    )

    signing_mock.assert_called_once_with(
        {
            "template": str(template.id),
            "template_version": job.template_version,
            "job": str(job.id),
            "to": "07900100100",
            "row_number": 0,
            "personalisation": {"name": "foo"},
            "client_reference": "ab1234",
        }
    )


# -------- save_sms and save_email tests -------- #


@pytest.mark.parametrize("client_reference", [None, "ab1234"])
def test_should_send_template_to_correct_sms_task_and_persist(
    sample_template_with_placeholders, mocker, client_reference
):
    notification = _notification_json(
        sample_template_with_placeholders,
        to="+447234123123",
        personalisation={"name": "Jo"},
        client_reference=client_reference,
    )

    mocked_deliver_sms = mocker.patch("app.celery.provider_tasks.deliver_sms.apply_async")

    save_sms(
        sample_template_with_placeholders.service_id,
        uuid.uuid4(),
        signing.encode(notification),
    )

    persisted_notification = Notification.query.one()
    assert persisted_notification.to == "+447234123123"
    assert persisted_notification.template_id == sample_template_with_placeholders.id
    assert persisted_notification.template_version == sample_template_with_placeholders.version
    assert persisted_notification.status == "created"
    assert persisted_notification.created_at <= datetime.now(UTC).replace(tzinfo=None)
    assert not persisted_notification.sent_at
    assert not persisted_notification.sent_by
    assert not persisted_notification.job_id
    assert persisted_notification.personalisation == {"name": "Jo"}
    assert persisted_notification._personalisation == signing.encode({"name": "Jo"})
    assert persisted_notification.notification_type == "sms"
    assert persisted_notification.client_reference == client_reference
    mocked_deliver_sms.assert_called_once_with([str(persisted_notification.id)], queue="send-sms-tasks")


def test_should_save_sms_if_restricted_service_and_valid_number(notify_db_session, mocker):
    user = create_user(mobile_number="07700 900890")
    service = create_service(user=user, restricted=True)
    template = create_template(service=service)
    notification = _notification_json(template, "+447700900890")  # The user’s own number, but in a different format

    mocker.patch("app.celery.provider_tasks.deliver_sms.apply_async")

    notification_id = uuid.uuid4()
    encode_notification = signing.encode(notification)
    save_sms(
        service.id,
        notification_id,
        encode_notification,
    )

    persisted_notification = Notification.query.one()
    assert persisted_notification.to == "+447700900890"
    assert persisted_notification.template_id == template.id
    assert persisted_notification.template_version == template.version
    assert persisted_notification.status == "created"
    assert persisted_notification.created_at <= datetime.now(UTC).replace(tzinfo=None)
    assert not persisted_notification.sent_at
    assert not persisted_notification.sent_by
    assert not persisted_notification.job_id
    assert not persisted_notification.personalisation
    assert persisted_notification.notification_type == "sms"
    provider_tasks.deliver_sms.apply_async.assert_called_once_with(
        [str(persisted_notification.id)], queue="send-sms-tasks"
    )


def test_save_email_should_save_default_email_reply_to_text_on_notification(notify_db_session, mocker):
    service = create_service()
    create_reply_to_email(service=service, email_address="reply_to@digital.gov.uk", is_default=True)
    template = create_template(service=service, template_type="email", subject="Hello")

    notification = _notification_json(template, to="test@example.com")
    mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")

    notification_id = uuid.uuid4()
    save_email(
        service.id,
        notification_id,
        signing.encode(notification),
    )

    persisted_notification = Notification.query.one()
    assert persisted_notification.reply_to_text == "reply_to@digital.gov.uk"


def test_save_sms_should_save_default_smm_sender_notification_reply_to_text_on(notify_db_session, mocker):
    service = create_service_with_defined_sms_sender(sms_sender_value="12345")
    template = create_template(service=service)

    notification = _notification_json(template, to="07700 900205")
    mocker.patch("app.celery.provider_tasks.deliver_sms.apply_async")

    notification_id = uuid.uuid4()
    save_sms(
        service.id,
        notification_id,
        signing.encode(notification),
    )

    persisted_notification = Notification.query.one()
    assert persisted_notification.reply_to_text == "12345"


def test_should_not_save_sms_if_restricted_service_and_invalid_number(notify_db_session, mocker):
    user = create_user(mobile_number="07700 900205")
    service = create_service(user=user, restricted=True)
    template = create_template(service=service)

    notification = _notification_json(template, "07700 900849")
    mocker.patch("app.celery.provider_tasks.deliver_sms.apply_async")

    notification_id = uuid.uuid4()
    save_sms(
        service.id,
        notification_id,
        signing.encode(notification),
    )
    assert provider_tasks.deliver_sms.apply_async.called is False
    assert Notification.query.count() == 0


def test_should_not_save_email_if_restricted_service_and_invalid_email_address(notify_db_session, mocker):
    user = create_user()
    service = create_service(user=user, restricted=True)
    template = create_template(service=service, template_type="email", subject="Hello")
    notification = _notification_json(template, to="test@example.com")

    notification_id = uuid.uuid4()
    save_email(
        service.id,
        notification_id,
        signing.encode(notification),
    )

    assert Notification.query.count() == 0


def test_should_save_sms_template_to_and_persist_with_job_id(sample_job, mocker):
    notification = _notification_json(sample_job.template, to="+447234123123", job_id=sample_job.id, row_number=2)
    mocker.patch("app.celery.provider_tasks.deliver_sms.apply_async")

    notification_id = uuid.uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)
    save_sms(
        sample_job.service.id,
        notification_id,
        signing.encode(notification),
    )
    persisted_notification = Notification.query.one()
    assert persisted_notification.to == "+447234123123"
    assert persisted_notification.job_id == sample_job.id
    assert persisted_notification.template_id == sample_job.template.id
    assert persisted_notification.status == "created"
    assert not persisted_notification.sent_at
    assert persisted_notification.created_at >= now
    assert not persisted_notification.sent_by
    assert persisted_notification.job_row_number == 2
    assert persisted_notification.api_key_id is None
    assert persisted_notification.key_type == KEY_TYPE_NORMAL
    assert persisted_notification.notification_type == "sms"

    provider_tasks.deliver_sms.apply_async.assert_called_once_with(
        [str(persisted_notification.id)], queue="send-sms-tasks"
    )


def test_should_not_save_sms_if_team_key_and_recipient_not_in_team(notify_db_session, mocker):
    assert Notification.query.count() == 0
    user = create_user(mobile_number="07700 900205")
    service = create_service(user=user, restricted=True)
    template = create_template(service=service)

    team_members = [user.mobile_number for user in service.users]
    assert "07890 300000" not in team_members

    notification = _notification_json(template, "07700 900849")
    mocker.patch("app.celery.provider_tasks.deliver_sms.apply_async")

    notification_id = uuid.uuid4()
    save_sms(
        service.id,
        notification_id,
        signing.encode(notification),
    )
    assert provider_tasks.deliver_sms.apply_async.called is False
    assert Notification.query.count() == 0


@pytest.mark.parametrize("client_reference", [None, "ab1234"])
def test_should_use_email_template_and_persist(
    sample_email_template_with_placeholders, sample_api_key, mocker, client_reference
):
    mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")

    now = datetime(2016, 1, 1, 11, 9, 0)
    notification_id = uuid.uuid4()

    with freeze_time("2016-01-01 12:00:00.000000"):
        notification = _notification_json(
            sample_email_template_with_placeholders,
            "my_email@my_email.com",
            {"name": "Jo"},
            row_number=1,
            client_reference=client_reference,
        )

    with freeze_time("2016-01-01 11:10:00.00000"):
        save_email(
            sample_email_template_with_placeholders.service_id,
            notification_id,
            signing.encode(notification),
        )

    persisted_notification = Notification.query.one()
    assert persisted_notification.to == "my_email@my_email.com"
    assert persisted_notification.template_id == sample_email_template_with_placeholders.id
    assert persisted_notification.template_version == sample_email_template_with_placeholders.version
    assert persisted_notification.created_at >= now
    assert not persisted_notification.sent_at
    assert persisted_notification.status == "created"
    assert not persisted_notification.sent_by
    assert persisted_notification.job_row_number == 1
    assert persisted_notification.personalisation == {"name": "Jo"}
    assert persisted_notification._personalisation == signing.encode({"name": "Jo"})
    assert persisted_notification.api_key_id is None
    assert persisted_notification.key_type == KEY_TYPE_NORMAL
    assert persisted_notification.notification_type == "email"
    assert persisted_notification.client_reference == client_reference

    provider_tasks.deliver_email.apply_async.assert_called_once_with(
        [str(persisted_notification.id)], queue="send-email-tasks"
    )


def test_save_email_should_use_template_version_from_job_not_latest(sample_email_template, mocker):
    notification = _notification_json(sample_email_template, "my_email@my_email.com")
    version_on_notification = sample_email_template.version
    # Change the template
    from app.dao.templates_dao import (
        dao_get_template_by_id,
        dao_update_template,
    )

    sample_email_template.content = sample_email_template.content + " another version of the template"
    mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")
    dao_update_template(sample_email_template)
    t = dao_get_template_by_id(sample_email_template.id)
    assert t.version > version_on_notification
    now = datetime.now(UTC).replace(tzinfo=None)
    save_email(
        sample_email_template.service_id,
        uuid.uuid4(),
        signing.encode(notification),
    )

    persisted_notification = Notification.query.one()
    assert persisted_notification.to == "my_email@my_email.com"
    assert persisted_notification.template_id == sample_email_template.id
    assert persisted_notification.template_version == version_on_notification
    assert persisted_notification.created_at >= now
    assert not persisted_notification.sent_at
    assert persisted_notification.status == "created"
    assert not persisted_notification.sent_by
    assert persisted_notification.notification_type == "email"
    provider_tasks.deliver_email.apply_async.assert_called_once_with(
        [str(persisted_notification.id)], queue="send-email-tasks"
    )


def test_should_use_email_template_subject_placeholders(sample_email_template_with_placeholders, mocker):
    notification = _notification_json(sample_email_template_with_placeholders, "my_email@my_email.com", {"name": "Jo"})
    mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")

    notification_id = uuid.uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)
    save_email(
        sample_email_template_with_placeholders.service_id,
        notification_id,
        signing.encode(notification),
    )
    persisted_notification = Notification.query.one()
    assert persisted_notification.to == "my_email@my_email.com"
    assert persisted_notification.template_id == sample_email_template_with_placeholders.id
    assert persisted_notification.status == "created"
    assert persisted_notification.created_at >= now
    assert not persisted_notification.sent_by
    assert persisted_notification.personalisation == {"name": "Jo"}
    assert not persisted_notification.reference
    assert persisted_notification.notification_type == "email"
    provider_tasks.deliver_email.apply_async.assert_called_once_with(
        [str(persisted_notification.id)], queue="send-email-tasks"
    )


def test_save_email_uses_the_reply_to_text_when_provided(sample_email_template, mocker):
    notification = _notification_json(sample_email_template, "my_email@my_email.com")
    mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")

    service = sample_email_template.service
    notification_id = uuid.uuid4()
    service_email_reply_to_dao.add_reply_to_email_address_for_service(service.id, "default@example.com", True)
    other_email_reply_to = service_email_reply_to_dao.add_reply_to_email_address_for_service(
        service.id, "other@example.com", False
    )

    save_email(
        sample_email_template.service_id,
        notification_id,
        signing.encode(notification),
        sender_id=other_email_reply_to.id,
    )
    persisted_notification = Notification.query.one()
    assert persisted_notification.notification_type == "email"
    assert persisted_notification.reply_to_text == "other@example.com"


def test_save_email_uses_the_default_reply_to_text_if_sender_id_is_none(sample_email_template, mocker):
    notification = _notification_json(sample_email_template, "my_email@my_email.com")
    mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")

    service = sample_email_template.service
    notification_id = uuid.uuid4()
    service_email_reply_to_dao.add_reply_to_email_address_for_service(service.id, "default@example.com", True)

    save_email(
        sample_email_template.service_id,
        notification_id,
        signing.encode(notification),
        sender_id=None,
    )
    persisted_notification = Notification.query.one()
    assert persisted_notification.notification_type == "email"
    assert persisted_notification.reply_to_text == "default@example.com"


def test_should_use_email_template_and_persist_without_personalisation(sample_email_template, mocker):
    notification = _notification_json(sample_email_template, "my_email@my_email.com")
    mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")

    notification_id = uuid.uuid4()

    now = datetime.now(UTC).replace(tzinfo=None)
    save_email(
        sample_email_template.service_id,
        notification_id,
        signing.encode(notification),
    )
    persisted_notification = Notification.query.one()
    assert persisted_notification.to == "my_email@my_email.com"
    assert persisted_notification.template_id == sample_email_template.id
    assert persisted_notification.created_at >= now
    assert not persisted_notification.sent_at
    assert persisted_notification.status == "created"
    assert not persisted_notification.sent_by
    assert not persisted_notification.personalisation
    assert not persisted_notification.reference
    assert persisted_notification.notification_type == "email"
    provider_tasks.deliver_email.apply_async.assert_called_once_with(
        [str(persisted_notification.id)], queue="send-email-tasks"
    )


def test_save_sms_should_go_to_retry_queue_if_database_errors(sample_template, mocker):
    notification = _notification_json(sample_template, "+447234123123")

    expected_exception = SQLAlchemyError()

    mocker.patch("app.celery.provider_tasks.deliver_sms.apply_async")
    mocker.patch("app.celery.tasks.save_sms.retry", side_effect=Retry)
    mocker.patch("app.notifications.process_notifications.dao_create_notification", side_effect=expected_exception)

    notification_id = uuid.uuid4()

    with pytest.raises(Retry):
        save_sms(
            sample_template.service_id,
            notification_id,
            signing.encode(notification),
        )
    assert provider_tasks.deliver_sms.apply_async.called is False
    tasks.save_sms.retry.assert_called_with(exc=expected_exception, queue="retry-tasks")

    assert Notification.query.count() == 0


def test_save_email_should_go_to_retry_queue_if_database_errors(sample_email_template, mocker):
    notification = _notification_json(sample_email_template, "test@example.gov.uk")

    expected_exception = SQLAlchemyError()

    mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")
    mocker.patch("app.celery.tasks.save_email.retry", side_effect=Retry)
    mocker.patch("app.notifications.process_notifications.dao_create_notification", side_effect=expected_exception)

    notification_id = uuid.uuid4()

    with pytest.raises(Retry):
        save_email(
            sample_email_template.service_id,
            notification_id,
            signing.encode(notification),
        )
    assert not provider_tasks.deliver_email.apply_async.called
    tasks.save_email.retry.assert_called_with(exc=expected_exception, queue="retry-tasks")

    assert Notification.query.count() == 0


def test_save_email_does_not_send_duplicate_and_does_not_put_in_retry_queue(sample_notification, mocker):
    json = _notification_json(sample_notification.template, sample_notification.to, job_id=uuid.uuid4(), row_number=1)
    deliver_email = mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")
    retry = mocker.patch("app.celery.tasks.save_email.retry", side_effect=Exception())

    notification_id = sample_notification.id

    save_email(
        sample_notification.service_id,
        notification_id,
        signing.encode(json),
    )
    assert Notification.query.count() == 1
    assert not deliver_email.called
    assert not retry.called


def test_save_sms_does_not_send_duplicate_and_does_not_put_in_retry_queue(sample_notification, mocker):
    json = _notification_json(sample_notification.template, sample_notification.to, job_id=uuid.uuid4(), row_number=1)
    deliver_sms = mocker.patch("app.celery.provider_tasks.deliver_sms.apply_async")
    retry = mocker.patch("app.celery.tasks.save_sms.retry", side_effect=Exception())

    notification_id = sample_notification.id

    save_sms(
        sample_notification.service_id,
        notification_id,
        signing.encode(json),
    )
    assert Notification.query.count() == 1
    assert not deliver_sms.called
    assert not retry.called


@pytest.mark.parametrize(
    "personalisation, expected_to, expected_normalised, client_reference",
    (
        (
            {
                "addressline1": "Foo",
                "addressline2": "Bar",
                "addressline3": "Baz",
                "addressline4": "Wibble",
                "addressline5": "Wobble",
                "addressline6": "Wubble",
                "postcode": "SE1 2SA",
            },
            ("Foo\n" "Bar\n" "Baz\n" "Wibble\n" "Wobble\n" "Wubble\n" "SE1 2SA"),
            ("foobarbazwibblewobblewubblese12sa"),
            None,
        ),
        (
            {
                # The address isn’t normalised when we store it in the
                # `personalisation` column, but is normalised for storing in the
                # `to` column
                "addressline2": "    Foo    ",
                "addressline4": "Bar",
                "addressline6": "se12sa",
            },
            ("Foo\n" "Bar\n" "SE1 2SA"),
            ("foobarse12sa"),
            "ab1234",
        ),
    ),
)
def test_save_letter_saves_letter_to_database(
    mocker, notify_db_session, personalisation, expected_to, expected_normalised, client_reference
):
    service = create_service()
    contact_block = create_letter_contact(service=service, contact_block="Address contact", is_default=True)
    template = create_template(service=service, template_type=LETTER_TYPE, reply_to=contact_block.id)
    job = create_job(template=template)

    mocker.patch("app.celery.tasks.create_random_identifier", return_value="this-is-random-in-real-life")
    mocker.patch("app.celery.letters_pdf_tasks.get_pdf_for_templated_letter.apply_async")

    notification_json = _notification_json(
        template=job.template,
        to="This is ignored for letters",
        personalisation=personalisation,
        job_id=job.id,
        row_number=1,
        client_reference=client_reference,
    )
    notification_id = uuid.uuid4()
    created_at = datetime.now(UTC).replace(tzinfo=None)

    save_letter(
        job.service_id,
        notification_id,
        signing.encode(notification_json),
    )

    notification_db = Notification.query.one()
    assert notification_db.id == notification_id
    assert notification_db.to == expected_to
    assert notification_db.normalised_to == expected_normalised
    assert notification_db.job_id == job.id
    assert notification_db.template_id == job.template.id
    assert notification_db.template_version == job.template.version
    assert notification_db.status == "created"
    assert notification_db.created_at >= created_at
    assert notification_db.notification_type == "letter"
    assert notification_db.sent_at is None
    assert notification_db.sent_by is None
    assert notification_db.personalisation == personalisation
    assert notification_db.reference == "this-is-random-in-real-life"
    assert notification_db.reply_to_text == contact_block.contact_block
    assert notification_db.client_reference == client_reference


@pytest.mark.parametrize(
    "last_line_of_address, postage, expected_postage, expected_international",
    [
        ("SW1 1AA", "first", "first", False),
        ("SW1 1AA", "second", "second", False),
        ("New Zealand", "second", "rest-of-world", True),
        ("France", "first", "europe", True),
    ],
)
def test_save_letter_saves_letter_to_database_with_correct_postage(
    mocker, notify_db_session, last_line_of_address, postage, expected_postage, expected_international
):
    service = create_service(service_permissions=[LETTER_TYPE])
    template = create_template(service=service, template_type=LETTER_TYPE, postage=postage)
    letter_job = create_job(template=template)

    mocker.patch("app.celery.letters_pdf_tasks.get_pdf_for_templated_letter.apply_async")
    notification_json = _notification_json(
        template=letter_job.template,
        to="Foo",
        personalisation={"addressline1": "Foo", "addressline2": "Bar", "postcode": last_line_of_address},
        job_id=letter_job.id,
        row_number=1,
    )
    notification_id = uuid.uuid4()
    save_letter(
        letter_job.service_id,
        notification_id,
        signing.encode(notification_json),
    )

    notification_db = Notification.query.one()
    assert notification_db.id == notification_id
    assert notification_db.postage == expected_postage
    assert notification_db.international == expected_international


def test_save_letter_saves_letter_to_database_with_formatted_postcode(mocker, notify_db_session):
    service = create_service(service_permissions=[LETTER_TYPE])
    template = create_template(service=service, template_type=LETTER_TYPE)
    letter_job = create_job(template=template)

    mocker.patch("app.celery.letters_pdf_tasks.get_pdf_for_templated_letter.apply_async")
    notification_json = _notification_json(
        template=letter_job.template,
        to="Foo",
        personalisation={"addressline1": "Foo", "addressline2": "Bar", "postcode": "se1 64sa"},
        job_id=letter_job.id,
        row_number=1,
    )
    notification_id = uuid.uuid4()
    save_letter(
        letter_job.service_id,
        notification_id,
        signing.encode(notification_json),
    )

    notification_db = Notification.query.one()
    assert notification_db.id == notification_id
    assert notification_db.personalisation["postcode"] == "se1 64sa"


def test_save_letter_saves_letter_to_database_right_reply_to(mocker, notify_db_session):
    service = create_service()
    create_letter_contact(service=service, contact_block="Address contact", is_default=True)
    template = create_template(service=service, template_type=LETTER_TYPE, reply_to=None)
    job = create_job(template=template)

    mocker.patch("app.celery.tasks.create_random_identifier", return_value="this-is-random-in-real-life")
    mocker.patch("app.celery.letters_pdf_tasks.get_pdf_for_templated_letter.apply_async")

    personalisation = {
        "addressline1": "Foo",
        "addressline2": "Bar",
        "addressline3": "Baz",
        "addressline4": "Wibble",
        "addressline5": "Wobble",
        "addressline6": "Wubble",
        "postcode": "SE1 3WS",
    }
    notification_json = _notification_json(
        template=job.template, to="Foo", personalisation=personalisation, job_id=job.id, row_number=1
    )
    notification_id = uuid.uuid4()
    created_at = datetime.now(UTC).replace(tzinfo=None)

    save_letter(
        job.service_id,
        notification_id,
        signing.encode(notification_json),
    )

    notification_db = Notification.query.one()
    assert notification_db.id == notification_id
    assert notification_db.to == ("Foo\n" "Bar\n" "Baz\n" "Wibble\n" "Wobble\n" "Wubble\n" "SE1 3WS")
    assert notification_db.job_id == job.id
    assert notification_db.template_id == job.template.id
    assert notification_db.template_version == job.template.version
    assert notification_db.status == "created"
    assert notification_db.created_at >= created_at
    assert notification_db.notification_type == "letter"
    assert notification_db.sent_at is None
    assert notification_db.sent_by is None
    assert notification_db.personalisation == personalisation
    assert notification_db.reference == "this-is-random-in-real-life"
    assert not notification_db.reply_to_text


def test_save_letter_uses_template_reply_to_text(mocker, notify_db_session):
    service = create_service()
    create_letter_contact(service=service, contact_block="Address contact", is_default=True)
    template_contact = create_letter_contact(
        service=service, contact_block="Template address contact", is_default=False
    )
    template = create_template(service=service, template_type=LETTER_TYPE, reply_to=template_contact.id)

    job = create_job(template=template)

    mocker.patch("app.celery.tasks.create_random_identifier", return_value="this-is-random-in-real-life")
    mocker.patch("app.celery.letters_pdf_tasks.get_pdf_for_templated_letter.apply_async")

    personalisation = {
        "addressline1": "Foo",
        "addressline2": "Bar",
        "postcode": "Flob",
    }
    notification_json = _notification_json(
        template=job.template, to="Foo", personalisation=personalisation, job_id=job.id, row_number=1
    )

    save_letter(
        job.service_id,
        uuid.uuid4(),
        signing.encode(notification_json),
    )

    notification_db = Notification.query.one()
    assert notification_db.reply_to_text == "Template address contact"


def test_save_sms_uses_sms_sender_reply_to_text(mocker, notify_db_session):
    service = create_service_with_defined_sms_sender(sms_sender_value="07123123123")
    template = create_template(service=service)

    notification = _notification_json(template, to="07700 900205")
    mocker.patch("app.celery.provider_tasks.deliver_sms.apply_async")

    notification_id = uuid.uuid4()
    save_sms(
        service.id,
        notification_id,
        signing.encode(notification),
    )

    persisted_notification = Notification.query.one()
    assert persisted_notification.reply_to_text == "447123123123"


def test_save_sms_uses_non_default_sms_sender_reply_to_text_if_provided(mocker, notify_db_session):
    service = create_service_with_defined_sms_sender(sms_sender_value="07123123123")
    template = create_template(service=service)
    new_sender = service_sms_sender_dao.dao_add_sms_sender_for_service(service.id, "new-sender", False)

    notification = _notification_json(template, to="07700 900205")
    mocker.patch("app.celery.provider_tasks.deliver_sms.apply_async")

    notification_id = uuid.uuid4()
    save_sms(
        service.id,
        notification_id,
        signing.encode(notification),
        sender_id=new_sender.id,
    )

    persisted_notification = Notification.query.one()
    assert persisted_notification.reply_to_text == "new-sender"


def test_save_letter_calls_get_pdf_for_templated_letter_task(mocker, notify_db_session, sample_letter_job):
    mock_create_letters_pdf = mocker.patch("app.celery.letters_pdf_tasks.get_pdf_for_templated_letter.apply_async")

    personalisation = {
        "addressline1": "Foo",
        "addressline2": "Bar",
        "postcode": "Flob",
    }
    notification_json = _notification_json(
        template=sample_letter_job.template,
        to="Foo",
        personalisation=personalisation,
        job_id=sample_letter_job.id,
        row_number=1,
    )
    notification_id = uuid.uuid4()

    save_letter(
        sample_letter_job.service_id,
        notification_id,
        signing.encode(notification_json),
    )

    assert mock_create_letters_pdf.called
    mock_create_letters_pdf.assert_called_once_with([str(notification_id)], queue=QueueNames.CREATE_LETTERS_PDF)


def test_should_cancel_job_if_service_is_inactive(sample_service, sample_job, mocker):
    sample_service.active = False

    mocker.patch("app.celery.tasks.s3.get_job_from_s3")
    mocker.patch("app.celery.tasks.process_row")

    process_job(sample_job.id)

    job = jobs_dao.dao_get_job_by_id(sample_job.id)
    assert job.job_status == "cancelled"
    s3.get_job_from_s3.assert_not_called()
    tasks.process_row.assert_not_called()


def test_get_email_template_instance(mocker, sample_email_template, sample_job):
    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=("", {}),
    )
    sample_job.template_id = sample_email_template.id
    (
        recipient_csv,
        template,
        _sender_id,
    ) = get_recipient_csv_and_template_and_sender_id(sample_job)

    assert isinstance(template, PlainTextEmailTemplate)
    assert recipient_csv.placeholders == ["email address"]


def test_get_sms_template_instance(mocker, sample_template, sample_job):
    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=("", {}),
    )
    sample_job.template = sample_template
    (
        recipient_csv,
        template,
        _sender_id,
    ) = get_recipient_csv_and_template_and_sender_id(sample_job)

    assert isinstance(template, SMSMessageTemplate)
    assert recipient_csv.placeholders == ["phone number"]


def test_get_letter_template_instance(mocker, sample_job):
    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=("", {}),
    )
    sample_contact_block = create_letter_contact(service=sample_job.service, contact_block="((reference number))")
    sample_template = create_template(
        service=sample_job.service,
        template_type=LETTER_TYPE,
        reply_to=sample_contact_block.id,
    )
    sample_job.template_id = sample_template.id

    (
        recipient_csv,
        template,
        _sender_id,
    ) = get_recipient_csv_and_template_and_sender_id(sample_job)

    assert isinstance(template, LetterPrintTemplate)
    assert template.contact_block == ("((reference number))")
    assert template.placeholders == {"reference number"}
    assert recipient_csv.placeholders == [
        "reference number",
        "address line 1",
        "address line 2",
        "address line 3",
        "address line 4",
        "address line 5",
        "address line 6",
        "postcode",
        "address line 7",
    ]


def test_send_inbound_sms_to_service_post_https_request_to_service(notify_api, sample_service):
    inbound_api = create_service_inbound_api(
        service=sample_service, url="https://some.service.gov.uk/", bearer_token="something_unique"
    )
    inbound_sms = create_inbound_sms(
        service=sample_service,
        notify_number="0751421",
        user_number="447700900111",
        provider_date=datetime(2017, 6, 20),
        content="Here is some content",
    )
    data = {
        "id": str(inbound_sms.id),
        "source_number": inbound_sms.user_number,
        "destination_number": inbound_sms.notify_number,
        "message": inbound_sms.content,
        "date_received": inbound_sms.provider_date.strftime(DATETIME_FORMAT),
    }

    with requests_mock.Mocker() as request_mock:
        request_mock.post(inbound_api.url, json={}, status_code=200)
        send_inbound_sms_to_service(inbound_sms.id, inbound_sms.service_id)
    assert request_mock.call_count == 1
    assert request_mock.request_history[0].url == inbound_api.url
    assert request_mock.request_history[0].method == "POST"
    assert request_mock.request_history[0].text == json.dumps(data)
    assert request_mock.request_history[0].headers["Content-type"] == "application/json"
    assert request_mock.request_history[0].headers["Authorization"] == "Bearer {}".format(inbound_api.bearer_token)


def test_send_inbound_sms_to_service_does_not_send_request_when_inbound_sms_does_not_exist(notify_api, sample_service):
    inbound_api = create_service_inbound_api(service=sample_service)
    with requests_mock.Mocker() as request_mock:
        request_mock.post(inbound_api.url, json={}, status_code=200)
        with pytest.raises(SQLAlchemyError):
            send_inbound_sms_to_service(inbound_sms_id=uuid.uuid4(), service_id=sample_service.id)

    assert request_mock.call_count == 0


def test_send_inbound_sms_to_service_does_not_sent_request_when_inbound_api_does_not_exist(
    notify_api, sample_service, mocker
):
    inbound_sms = create_inbound_sms(
        service=sample_service,
        notify_number="0751421",
        user_number="447700900111",
        provider_date=datetime(2017, 6, 20),
        content="Here is some content",
    )
    mocked = mocker.patch("requests.request")
    send_inbound_sms_to_service(inbound_sms.id, inbound_sms.service_id)

    assert mocked.call_count == 0


def test_send_inbound_sms_to_service_retries_if_request_returns_500(notify_api, sample_service, mocker):
    inbound_api = create_service_inbound_api(
        service=sample_service, url="https://some.service.gov.uk/", bearer_token="something_unique"
    )
    inbound_sms = create_inbound_sms(
        service=sample_service,
        notify_number="0751421",
        user_number="447700900111",
        provider_date=datetime(2017, 6, 20),
        content="Here is some content",
    )

    mocked = mocker.patch("app.celery.tasks.send_inbound_sms_to_service.retry")
    with requests_mock.Mocker() as request_mock:
        request_mock.post(inbound_api.url, json={}, status_code=500)
        send_inbound_sms_to_service(inbound_sms.id, inbound_sms.service_id)

    assert mocked.call_count == 1
    assert mocked.call_args[1]["queue"] == "retry-tasks"


def test_send_inbound_sms_to_service_retries_if_request_throws_unknown(notify_api, sample_service, mocker):
    create_service_inbound_api(
        service=sample_service, url="https://some.service.gov.uk/", bearer_token="something_unique"
    )
    inbound_sms = create_inbound_sms(
        service=sample_service,
        notify_number="0751421",
        user_number="447700900111",
        provider_date=datetime(2017, 6, 20),
        content="Here is some content",
    )

    mocked = mocker.patch("app.celery.tasks.send_inbound_sms_to_service.retry")
    mocker.patch("app.celery.tasks.request", side_effect=RequestException())

    send_inbound_sms_to_service(inbound_sms.id, inbound_sms.service_id)

    assert mocked.call_count == 1
    assert mocked.call_args[1]["queue"] == "retry-tasks"


def test_send_inbound_sms_to_service_does_not_retries_if_request_returns_404(notify_api, sample_service, mocker):
    inbound_api = create_service_inbound_api(
        service=sample_service, url="https://some.service.gov.uk/", bearer_token="something_unique"
    )
    inbound_sms = create_inbound_sms(
        service=sample_service,
        notify_number="0751421",
        user_number="447700900111",
        provider_date=datetime(2017, 6, 20),
        content="Here is some content",
    )

    mocked = mocker.patch("app.celery.tasks.send_inbound_sms_to_service.retry")
    with requests_mock.Mocker() as request_mock:
        request_mock.post(inbound_api.url, json={}, status_code=404)
        send_inbound_sms_to_service(inbound_sms.id, inbound_sms.service_id)

    assert mocked.call_count == 0


def test_process_incomplete_job_sms(mocker, sample_template):
    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=(load_example_csv("multiple_sms"), {"sender_id": None}),
    )
    save_sms = mocker.patch("app.celery.tasks.save_sms.apply_async")

    job = create_job(
        template=sample_template,
        notification_count=10,
        created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=2),
        scheduled_for=datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=31),
        processing_started=datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=31),
        job_status=JOB_STATUS_ERROR,
    )

    create_notification(sample_template, job, 0)
    create_notification(sample_template, job, 1)

    assert Notification.query.filter(Notification.job_id == job.id).count() == 2

    process_incomplete_job(str(job.id))

    completed_job = Job.query.filter(Job.id == job.id).one()

    assert completed_job.job_status == JOB_STATUS_FINISHED

    assert save_sms.call_count == 8  # There are 10 in the file and we've added two already


def test_process_incomplete_job_with_notifications_all_sent(mocker, sample_template):
    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=(load_example_csv("multiple_sms"), {"sender_id": None}),
    )
    mock_save_sms = mocker.patch("app.celery.tasks.save_sms.apply_async")

    job = create_job(
        template=sample_template,
        notification_count=10,
        created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=2),
        scheduled_for=datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=31),
        processing_started=datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=31),
        job_status=JOB_STATUS_ERROR,
    )

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
    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=(load_example_csv("multiple_sms"), {"sender_id": None}),
    )
    mock_save_sms = mocker.patch("app.celery.tasks.save_sms.apply_async")

    job = create_job(
        template=sample_template,
        notification_count=10,
        created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=2),
        scheduled_for=datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=31),
        processing_started=datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=31),
        job_status=JOB_STATUS_ERROR,
    )
    create_notification(sample_template, job, 0)
    create_notification(sample_template, job, 1)
    create_notification(sample_template, job, 2)

    assert Notification.query.filter(Notification.job_id == job.id).count() == 3

    job2 = create_job(
        template=sample_template,
        notification_count=10,
        created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=2),
        scheduled_for=datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=31),
        processing_started=datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=31),
        job_status=JOB_STATUS_ERROR,
    )

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
    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=(load_example_csv("multiple_sms"), {"sender_id": None}),
    )
    mock_save_sms = mocker.patch("app.celery.tasks.save_sms.apply_async")

    job = create_job(
        template=sample_template,
        notification_count=10,
        created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=2),
        scheduled_for=datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=31),
        processing_started=datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=31),
        job_status=JOB_STATUS_ERROR,
    )

    assert Notification.query.filter(Notification.job_id == job.id).count() == 0

    process_incomplete_job(job.id)

    completed_job = Job.query.filter(Job.id == job.id).one()

    assert completed_job.job_status == JOB_STATUS_FINISHED

    assert mock_save_sms.call_count == 10  # There are 10 in the csv file


def test_process_incomplete_jobs(mocker):
    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=(load_example_csv("multiple_sms"), {"sender_id": None}),
    )
    mock_save_sms = mocker.patch("app.celery.tasks.save_sms.apply_async")

    jobs = []
    process_incomplete_jobs(jobs)

    assert mock_save_sms.call_count == 0  # There are no jobs to process so it will not have been called


def test_process_incomplete_job_no_job_in_database(mocker, fake_uuid):
    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=(load_example_csv("multiple_sms"), {"sender_id": None}),
    )
    mock_save_sms = mocker.patch("app.celery.tasks.save_sms.apply_async")

    with pytest.raises(expected_exception=Exception):
        process_incomplete_job(fake_uuid)

    assert mock_save_sms.call_count == 0  # There is no job in the db it will not have been called


def test_process_incomplete_job_email(mocker, sample_email_template):
    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=(load_example_csv("multiple_email"), {"sender_id": None}),
    )
    mock_email_saver = mocker.patch("app.celery.tasks.save_email.apply_async")

    job = create_job(
        template=sample_email_template,
        notification_count=10,
        created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=2),
        scheduled_for=datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=31),
        processing_started=datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=31),
        job_status=JOB_STATUS_ERROR,
    )

    create_notification(sample_email_template, job, 0)
    create_notification(sample_email_template, job, 1)

    assert Notification.query.filter(Notification.job_id == job.id).count() == 2

    process_incomplete_job(str(job.id))

    completed_job = Job.query.filter(Job.id == job.id).one()

    assert completed_job.job_status == JOB_STATUS_FINISHED

    assert mock_email_saver.call_count == 8  # There are 10 in the file and we've added two already


def test_process_incomplete_job_letter(mocker, sample_letter_template):
    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=(load_example_csv("multiple_letter"), {"sender_id": None}),
    )
    mock_letter_saver = mocker.patch("app.celery.tasks.save_letter.apply_async")

    job = create_job(
        template=sample_letter_template,
        notification_count=10,
        created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=2),
        scheduled_for=datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=31),
        processing_started=datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=31),
        job_status=JOB_STATUS_ERROR,
    )

    create_notification(sample_letter_template, job, 0)
    create_notification(sample_letter_template, job, 1)

    assert Notification.query.filter(Notification.job_id == job.id).count() == 2

    process_incomplete_job(str(job.id))

    assert mock_letter_saver.call_count == 8


@freeze_time("2017-01-01")
def test_process_incomplete_jobs_sets_status_to_in_progress_and_resets_processing_started_time(mocker, sample_template):
    mock_process_incomplete_job = mocker.patch("app.celery.tasks.process_incomplete_job")

    job1 = create_job(
        sample_template,
        processing_started=datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=30),
        job_status=JOB_STATUS_ERROR,
    )
    job2 = create_job(
        sample_template,
        processing_started=datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=31),
        job_status=JOB_STATUS_ERROR,
    )

    process_incomplete_jobs([str(job1.id), str(job2.id)])

    assert job1.job_status == JOB_STATUS_IN_PROGRESS
    assert job1.processing_started == datetime.now(UTC).replace(tzinfo=None)

    assert job2.job_status == JOB_STATUS_IN_PROGRESS
    assert job2.processing_started == datetime.now(UTC).replace(tzinfo=None)

    assert mock_process_incomplete_job.mock_calls == [call(str(job1.id)), call(str(job2.id))]


def test_process_returned_letters_list(sample_letter_template):
    create_notification(sample_letter_template, reference="ref1")
    create_notification(sample_letter_template, reference="ref2")

    process_returned_letters_list(["ref1", "ref2", "unknown-ref"])

    notifications = Notification.query.all()

    assert [n.status for n in notifications] == ["returned-letter", "returned-letter"]
    assert all(n.updated_at for n in notifications)


def test_process_returned_letters_list_updates_history_if_notification_is_already_purged(sample_letter_template):
    create_notification_history(sample_letter_template, reference="ref1")
    create_notification_history(sample_letter_template, reference="ref2")

    process_returned_letters_list(["ref1", "ref2", "unknown-ref"])

    notifications = NotificationHistory.query.all()

    assert [n.status for n in notifications] == ["returned-letter", "returned-letter"]
    assert all(n.updated_at for n in notifications)


def test_process_returned_letters_populates_returned_letters_table(sample_letter_template):
    create_notification_history(sample_letter_template, reference="ref1")
    create_notification_history(sample_letter_template, reference="ref2")

    process_returned_letters_list(["ref1", "ref2", "unknown-ref"])

    returned_letters = ReturnedLetter.query.all()
    assert len(returned_letters) == 2


@freeze_time("2020-03-25 14:30")
@pytest.mark.parametrize("notification_type", ["sms", "email"])
def test_save_api_email_or_sms(mocker, sample_service, notification_type):
    template = (
        create_template(sample_service)
        if notification_type == SMS_TYPE
        else create_template(sample_service, template_type=EMAIL_TYPE)
    )
    mock_provider_task = mocker.patch(f"app.celery.provider_tasks.deliver_{notification_type}.apply_async")
    api_key = create_api_key(service=template.service)
    data = {
        "id": str(uuid.uuid4()),
        "template_id": str(template.id),
        "template_version": template.version,
        "service_id": str(template.service_id),
        "personalisation": None,
        "notification_type": template.template_type,
        "api_key_id": str(api_key.id),
        "key_type": api_key.key_type,
        "client_reference": "our email",
        "reply_to_text": None,
        "document_download_count": 0,
        "status": NOTIFICATION_CREATED,
        "created_at": datetime.now(UTC).replace(tzinfo=None).strftime(DATETIME_FORMAT),
    }

    if notification_type == EMAIL_TYPE:
        data.update({"to": "jane.citizen@example.com"})
        expected_queue = QueueNames.SEND_EMAIL
    else:
        data.update({"to": "+447700900855"})
        expected_queue = QueueNames.SEND_SMS

    encoded = signing.encode(data)

    assert len(Notification.query.all()) == 0
    if notification_type == EMAIL_TYPE:
        save_api_email(encoded_notification=encoded)
    else:
        save_api_sms(encoded_notification=encoded)
    notifications = Notification.query.all()
    assert len(notifications) == 1
    assert str(notifications[0].id) == data["id"]
    assert notifications[0].created_at == datetime(2020, 3, 25, 14, 30)
    assert notifications[0].notification_type == notification_type
    mock_provider_task.assert_called_once_with([data["id"]], queue=expected_queue)


@freeze_time("2020-03-25 14:30")
@pytest.mark.parametrize("notification_type", ["sms", "email"])
def test_save_api_email_dont_retry_if_notification_already_exists(sample_service, mocker, notification_type):
    template = (
        create_template(sample_service)
        if notification_type == SMS_TYPE
        else create_template(sample_service, template_type=EMAIL_TYPE)
    )
    mock_provider_task = mocker.patch(f"app.celery.provider_tasks.deliver_{notification_type}.apply_async")
    api_key = create_api_key(service=template.service)
    data = {
        "id": str(uuid.uuid4()),
        "template_id": str(template.id),
        "template_version": template.version,
        "service_id": str(template.service_id),
        "personalisation": None,
        "notification_type": template.template_type,
        "api_key_id": str(api_key.id),
        "key_type": api_key.key_type,
        "client_reference": "our email",
        "reply_to_text": "our.email@gov.uk",
        "document_download_count": 0,
        "status": NOTIFICATION_CREATED,
        "created_at": datetime.now(UTC).replace(tzinfo=None).strftime(DATETIME_FORMAT),
    }

    if notification_type == EMAIL_TYPE:
        data.update({"to": "jane.citizen@example.com"})
        expected_queue = QueueNames.SEND_EMAIL
    else:
        data.update({"to": "+447700900855"})
        expected_queue = QueueNames.SEND_SMS

    encoded = signing.encode(data)
    assert len(Notification.query.all()) == 0

    if notification_type == EMAIL_TYPE:
        save_api_email(encoded_notification=encoded)
    else:
        save_api_sms(encoded_notification=encoded)
    notifications = Notification.query.all()
    assert len(notifications) == 1
    # call the task again with the same notification
    if notification_type == EMAIL_TYPE:
        save_api_email(encoded_notification=encoded)
    else:
        save_api_sms(encoded_notification=encoded)
    notifications = Notification.query.all()
    assert len(notifications) == 1
    assert str(notifications[0].id) == data["id"]
    assert notifications[0].created_at == datetime(2020, 3, 25, 14, 30)
    # should only have sent the notification once.
    mock_provider_task.assert_called_once_with([data["id"]], queue=expected_queue)


@pytest.mark.parametrize(
    "task_function, delivery_mock, recipient, template_args",
    (
        (
            save_email,
            "app.celery.provider_tasks.deliver_email.apply_async",
            "test@example.com",
            {"template_type": "email", "subject": "Hello"},
        ),
        (save_sms, "app.celery.provider_tasks.deliver_sms.apply_async", "07700 900890", {"template_type": "sms"}),
        (
            save_letter,
            "app.celery.letters_pdf_tasks.get_pdf_for_templated_letter.apply_async",
            "123 Example Street\nCity of Town\nXM4 5HQ",
            {"template_type": "letter", "subject": "Hello"},
        ),
    ),
)
def test_save_tasks_use_cached_service_and_template(
    notify_db_session,
    mocker,
    task_function,
    delivery_mock,
    recipient,
    template_args,
):
    service = create_service()
    template = create_template(service=service, **template_args)

    notification = _notification_json(template, to=recipient)
    delivery_mock = mocker.patch(delivery_mock)
    service_dict_mock = mocker.patch(
        "app.serialised_models.SerialisedService.get_dict",
        wraps=SerialisedService.get_dict,
    )
    template_dict_mock = mocker.patch(
        "app.serialised_models.SerialisedTemplate.get_dict",
        wraps=SerialisedTemplate.get_dict,
    )

    for _ in range(3):
        task_function(
            service.id,
            uuid.uuid4(),
            signing.encode(notification),
        )

    # We talk to the database once for the service and once for the
    # template; subsequent calls are caught by the in memory cache
    assert service_dict_mock.call_args_list == [
        call(service.id),
    ]
    assert template_dict_mock.call_args_list == [
        call(str(template.id), str(service.id), 1),
    ]

    # But we save 3 notifications and enqueue 3 tasks
    assert len(Notification.query.all()) == 3
    assert len(delivery_mock.call_args_list) == 3


@freeze_time("2020-03-25 14:30")
@pytest.mark.parametrize(
    "notification_type, task_function, expected_queue, recipient",
    (
        ("sms", save_api_sms, QueueNames.SEND_SMS, "+447700900855"),
        ("email", save_api_email, QueueNames.SEND_EMAIL, "jane.citizen@example.com"),
    ),
)
def test_save_api_tasks_use_cache(
    sample_service,
    mocker,
    notification_type,
    task_function,
    expected_queue,
    recipient,
):
    mock_provider_task = mocker.patch(f"app.celery.provider_tasks.deliver_{notification_type}.apply_async")
    service_dict_mock = mocker.patch(
        "app.serialised_models.SerialisedService.get_dict",
        wraps=SerialisedService.get_dict,
    )

    template = create_template(sample_service, template_type=notification_type)
    api_key = create_api_key(service=template.service)

    def create_encoded_notification():
        return signing.encode(
            {
                "to": recipient,
                "id": str(uuid.uuid4()),
                "template_id": str(template.id),
                "template_version": template.version,
                "service_id": str(template.service_id),
                "personalisation": None,
                "notification_type": template.template_type,
                "api_key_id": str(api_key.id),
                "key_type": api_key.key_type,
                "client_reference": "our email",
                "reply_to_text": "our.email@gov.uk",
                "document_download_count": 0,
                "status": NOTIFICATION_CREATED,
                "created_at": datetime.now(UTC).replace(tzinfo=None).strftime(DATETIME_FORMAT),
            }
        )

    assert len(Notification.query.all()) == 0

    for _ in range(3):
        task_function(encoded_notification=create_encoded_notification())

    assert service_dict_mock.call_args_list == [call(str(template.service_id))]

    assert len(Notification.query.all()) == 3
    assert len(mock_provider_task.call_args_list) == 3
