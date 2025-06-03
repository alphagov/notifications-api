import datetime
import uuid
from collections import namedtuple

import pytest
from boto3.exceptions import Boto3Error
from freezegun import freeze_time
from notifications_utils.recipient_validation.email_address import (
    validate_and_format_email_address,
)
from sqlalchemy.exc import SQLAlchemyError

from app.constants import (
    EMAIL_TYPE,
    KEY_TYPE_NORMAL,
    LETTER_TYPE,
    SMS_TYPE,
)
from app.models import Notification, NotificationHistory
from app.notifications.process_notifications import (
    create_content_for_notification,
    persist_notification,
    send_notification_to_queue,
    simulated_recipient,
)
from app.serialised_models import SerialisedTemplate
from app.utils import parse_and_format_phone_number
from app.v2.errors import BadRequestError, QrCodeTooLongError
from tests.app.db import create_api_key, create_job, create_service, create_template
from tests.conftest import set_config


def test_create_content_for_notification_passes(sample_email_template):
    template = SerialisedTemplate.from_id_and_service_id(sample_email_template.id, sample_email_template.service_id)
    content = create_content_for_notification(template, None)
    assert str(content) == template.content + "\n"


def test_create_content_for_notification_with_placeholders_passes(
    sample_template_with_placeholders,
):
    template = SerialisedTemplate.from_id_and_service_id(
        sample_template_with_placeholders.id,
        sample_template_with_placeholders.service_id,
    )
    content = create_content_for_notification(template, {"name": "Bobby"})
    assert content.content == template.content
    assert "Bobby" in str(content)


def test_create_content_for_notification_fails_with_missing_personalisation(
    sample_template_with_placeholders,
):
    template = SerialisedTemplate.from_id_and_service_id(
        sample_template_with_placeholders.id,
        sample_template_with_placeholders.service_id,
    )
    with pytest.raises(BadRequestError):
        create_content_for_notification(template, None)


def test_create_content_for_notification_allows_additional_personalisation(
    sample_template_with_placeholders,
):
    template = SerialisedTemplate.from_id_and_service_id(
        sample_template_with_placeholders.id,
        sample_template_with_placeholders.service_id,
    )
    create_content_for_notification(template, {"name": "Bobby", "Additional placeholder": "Data"})


def test_create_content_for_notification_raises_error_on_qr_code_too_long(
    sample_service,
):
    db_template = create_template(sample_service, template_type=LETTER_TYPE, content="qr: ((code))")
    template = SerialisedTemplate.from_id_and_service_id(db_template.id, db_template.service_id)

    with pytest.raises(QrCodeTooLongError) as e:
        create_content_for_notification(template, {"code": "too much data " * 50})

    assert e.value.message == "Cannot create a usable QR code - the link is too long"
    assert e.value.num_bytes == 700
    assert e.value.max_bytes == 504
    assert e.value.data == "too much data " * 50


@freeze_time("2016-01-01 11:09:00.061258")
def test_persist_notification_creates_and_save_to_db(sample_template, sample_api_key, sample_job):
    assert Notification.query.count() == 0
    assert NotificationHistory.query.count() == 0
    notification = persist_notification(
        template_id=sample_template.id,
        template_version=sample_template.version,
        recipient={
            "unformatted_recipient": "+447111111111",
            "normalised_to": "447111111111",
            "international": False,
            "phone_prefix": "44",
            "rate_multiplier": 1,
        },
        service=sample_template.service,
        personalisation={},
        notification_type=SMS_TYPE,
        api_key_id=sample_api_key.id,
        key_type=sample_api_key.key_type,
        job_id=sample_job.id,
        job_row_number=100,
        reference="ref",
        reply_to_text=sample_template.service.get_default_sms_sender(),
    )

    assert Notification.query.get(notification.id) is not None

    notification_from_db = Notification.query.one()

    assert notification_from_db.id == notification.id
    assert notification_from_db.template_id == notification.template_id
    assert notification_from_db.template_version == notification.template_version
    assert notification_from_db.api_key_id == notification.api_key_id
    assert notification_from_db.key_type == notification.key_type
    assert notification_from_db.key_type == notification.key_type
    assert notification_from_db.billable_units == notification.billable_units
    assert notification_from_db.notification_type == notification.notification_type
    assert notification_from_db.created_at == notification.created_at
    assert not notification_from_db.sent_at
    assert notification_from_db.updated_at == notification.updated_at
    assert notification_from_db.status == notification.status
    assert notification_from_db.reference == notification.reference
    assert notification_from_db.client_reference == notification.client_reference
    assert notification_from_db.created_by_id == notification.created_by_id
    assert notification_from_db.reply_to_text == sample_template.service.get_default_sms_sender()


def test_persist_notification_throws_exception_when_missing_template(sample_api_key):
    assert Notification.query.count() == 0
    assert NotificationHistory.query.count() == 0
    with pytest.raises(SQLAlchemyError):
        persist_notification(
            template_id=None,
            template_version=None,
            recipient={
                "unformatted_recipient": "+447111111111",
                "normalised_to": "447111111111",
                "international": False,
                "phone_prefix": "44",
                "rate_multiplier": 1,
            },
            service=sample_api_key.service,
            personalisation=None,
            notification_type=SMS_TYPE,
            api_key_id=sample_api_key.id,
            key_type=sample_api_key.key_type,
        )
    assert Notification.query.count() == 0
    assert NotificationHistory.query.count() == 0


@freeze_time("2016-01-01 11:09:00.061258")
def test_persist_notification_with_optionals(sample_job, sample_api_key):
    assert Notification.query.count() == 0
    assert NotificationHistory.query.count() == 0
    n_id = uuid.uuid4()
    created_at = datetime.datetime(2016, 11, 11, 16, 8, 18)
    persist_notification(
        template_id=sample_job.template.id,
        template_version=sample_job.template.version,
        recipient={
            "unformatted_recipient": "+447111111111",
            "normalised_to": "447111111111",
            "international": False,
            "phone_prefix": "44",
            "rate_multiplier": 1,
        },
        service=sample_job.service,
        personalisation=None,
        notification_type=SMS_TYPE,
        api_key_id=sample_api_key.id,
        key_type=sample_api_key.key_type,
        created_at=created_at,
        job_id=sample_job.id,
        job_row_number=10,
        client_reference="ref from client",
        notification_id=n_id,
        created_by_id=sample_job.created_by_id,
    )
    assert Notification.query.count() == 1
    assert NotificationHistory.query.count() == 0
    persisted_notification = Notification.query.all()[0]
    assert persisted_notification.id == n_id
    assert persisted_notification.job_id == sample_job.id
    assert persisted_notification.job_row_number == 10
    assert persisted_notification.created_at == created_at

    assert persisted_notification.client_reference == "ref from client"
    assert persisted_notification.reference is None
    assert persisted_notification.international is False
    assert persisted_notification.phone_prefix == "44"
    assert persisted_notification.rate_multiplier == 1
    assert persisted_notification.created_by_id == sample_job.created_by_id
    assert not persisted_notification.reply_to_text


@pytest.mark.parametrize(
    "recipient, notification_type",
    [
        (
            {
                "unformatted_recipient": "+447111111111",
                "normalised_to": "447111111111",
                "international": False,
                "phone_prefix": "44",
                "rate_multiplier": 1,
            },
            SMS_TYPE,
        ),
        ("test@notifications.service.gov.uk", EMAIL_TYPE),
    ],
)
def test_persist_notification_cache_is_not_incremented_on_failure_to_create_notification(
    notify_api, sample_api_key, mocker, recipient, notification_type
):
    mocked_redis = mocker.patch("app.redis_store.incr")
    with pytest.raises(SQLAlchemyError):
        persist_notification(
            template_id=None,
            template_version=None,
            recipient=recipient,
            service=sample_api_key.service,
            personalisation=None,
            notification_type=notification_type,
            api_key_id=sample_api_key.id,
            key_type=sample_api_key.key_type,
        )
    mocked_redis.assert_not_called()


@pytest.mark.parametrize(
    "recipient, notification_type",
    [
        (
            {
                "unformatted_recipient": "+447111111111",
                "normalised_to": "447111111111",
                "international": False,
                "phone_prefix": "44",
                "rate_multiplier": 1,
            },
            SMS_TYPE,
        ),
        ("test@notifications.service.gov.uk", EMAIL_TYPE),
    ],
)
def test_persist_notification_does_not_increment_cache_if_test_key(
    notify_api, sample_template, sample_job, mocker, sample_test_api_key, recipient, notification_type
):
    daily_limit_cache = mocker.patch("app.notifications.process_notifications.redis_store.incr")

    assert Notification.query.count() == 0
    assert NotificationHistory.query.count() == 0
    with set_config(notify_api, "REDIS_ENABLED", True):
        persist_notification(
            template_id=sample_template.id,
            template_version=sample_template.version,
            recipient=recipient,
            service=sample_template.service,
            personalisation={},
            notification_type=notification_type,
            api_key_id=sample_test_api_key.id,
            key_type=sample_test_api_key.key_type,
            job_id=sample_job.id,
            job_row_number=100,
            reference="ref",
        )

    assert Notification.query.count() == 1

    assert not daily_limit_cache.called


@pytest.mark.parametrize(
    "recipient, notification_type",
    [
        (
            {
                "unformatted_recipient": "+447111111111",
                "normalised_to": "447111111111",
                "international": False,
                "phone_prefix": "44",
                "rate_multiplier": 1,
            },
            SMS_TYPE,
        ),
        ("test@notifications.service.gov.uk", EMAIL_TYPE),
    ],
)
@pytest.mark.parametrize("restricted_service", [True, False])
@freeze_time("2016-01-01 11:09:00.061258")
def test_persist_notification_increments_cache_for_trial_or_live_service(
    notify_api, notify_db_session, mocker, restricted_service, recipient, notification_type
):
    service = create_service(restricted=restricted_service)
    template = create_template(service=service)
    api_key = create_api_key(service=service)
    mocker.patch("app.notifications.process_notifications.redis_store.get", return_value=1)
    mock_incr = mocker.patch("app.notifications.process_notifications.redis_store.incr")
    with set_config(notify_api, "REDIS_ENABLED", True):
        persist_notification(
            template_id=template.id,
            template_version=template.version,
            recipient={
                "unformatted_recipient": "+447111111111",
                "normalised_to": "447111111111",
                "international": False,
                "phone_prefix": "44",
                "rate_multiplier": 1,
            },
            service=template.service,
            personalisation={},
            notification_type=SMS_TYPE,
            api_key_id=api_key.id,
            key_type=api_key.key_type,
            reference="ref2",
        )

        assert mock_incr.call_args_list == [
            mocker.call(f"{service.id}-sms-2016-01-01-count"),
        ]


@pytest.mark.parametrize("restricted_service", [True, False])
@freeze_time("2016-01-01 11:09:00.061258")
def test_persist_notification_sets_daily_limit_cache_if_one_does_not_exist(
    notify_api, notify_db_session, mocker, restricted_service
):
    service = create_service(restricted=restricted_service)
    template = create_template(service=service)
    api_key = create_api_key(service=service)
    mocker.patch("app.notifications.process_notifications.redis_store.get", return_value=None)
    mock_set = mocker.patch("app.notifications.process_notifications.redis_store.set")
    with set_config(notify_api, "REDIS_ENABLED", True):
        persist_notification(
            template_id=template.id,
            template_version=template.version,
            recipient={
                "unformatted_recipient": "+447111111111",
                "normalised_to": "447111111111",
                "international": False,
                "phone_prefix": "44",
                "rate_multiplier": 1,
            },
            service=template.service,
            personalisation={},
            notification_type=SMS_TYPE,
            api_key_id=api_key.id,
            key_type=api_key.key_type,
            reference="ref2",
        )

        assert mock_set.call_args_list == [
            mocker.call(f"{service.id}-sms-2016-01-01-count", 1, ex=86400),
        ]


@freeze_time("2016-01-01 11:09:00.061258")
def test_persist_notification_increments_cache_for_international_sms(notify_api, notify_db_session, mocker):
    service = create_service()
    template = create_template(service=service, template_type=SMS_TYPE)
    api_key = create_api_key(service=service)
    mocker.patch("app.notifications.process_notifications.redis_store.get", return_value=1)
    mock_incr = mocker.patch("app.notifications.process_notifications.redis_store.incr")
    with set_config(notify_api, "REDIS_ENABLED", True):
        persist_notification(
            template_id=template.id,
            template_version=template.version,
            recipient={
                "unformatted_recipient": "+48697894064",
                "normalised_to": "48697894064",
                "international": True,
                "phone_prefix": "48",
                "rate_multiplier": 2,
            },
            service=template.service,
            personalisation={},
            notification_type=SMS_TYPE,
            api_key_id=api_key.id,
            key_type=api_key.key_type,
            reference="ref2",
        )

        assert mock_incr.call_args_list == [
            mocker.call(f"{service.id}-sms-2016-01-01-count"),
            mocker.call(f"{service.id}-international_sms-2016-01-01-count"),
        ]


@freeze_time("2016-01-01 11:09:00.061258")
def test_persist_notification_doesnt_increment_cache_for_international_sms_when_num_is_crown_dependency(
    notify_api, notify_db_session, mocker
):
    service = create_service()
    template = create_template(service=service, template_type=SMS_TYPE)
    api_key = create_api_key(service=service)
    mocker.patch("app.notifications.process_notifications.redis_store.get", return_value=1)
    mock_incr = mocker.patch("app.notifications.process_notifications.redis_store.incr")
    with set_config(notify_api, "REDIS_ENABLED", True):
        persist_notification(
            template_id=template.id,
            template_version=template.version,
            recipient={
                "unformatted_recipient": "+44 7797 100 100",
                "normalised_to": "+447797100100",
                "international": True,
                "phone_prefix": "44",
                "rate_multiplier": 2,
            },
            service=template.service,
            personalisation={},
            notification_type=SMS_TYPE,
            api_key_id=api_key.id,
            key_type=api_key.key_type,
            reference="ref2",
        )

        assert mock_incr.call_args_list == [
            mocker.call(f"{service.id}-sms-2016-01-01-count"),
        ]


@freeze_time("2016-01-01 11:09:00.061258")
def test_persist_notification_doesnt_increment_cache_for_international_sms_with_email(
    notify_api, notify_db_session, mocker
):
    service = create_service()
    template = create_template(service=service, template_type=EMAIL_TYPE)
    api_key = create_api_key(service=service)
    mocker.patch("app.notifications.process_notifications.redis_store.get", return_value=1)
    mock_incr = mocker.patch("app.notifications.process_notifications.redis_store.incr")
    with set_config(notify_api, "REDIS_ENABLED", True):
        persist_notification(
            template_id=template.id,
            template_version=template.version,
            recipient="example@email.com",
            service=template.service,
            personalisation={},
            notification_type=EMAIL_TYPE,
            api_key_id=api_key.id,
            key_type=api_key.key_type,
        )

        assert mock_incr.call_args_list == [
            mocker.call(f"{service.id}-email-2016-01-01-count"),
        ]


@freeze_time("2016-01-01 11:09:00.061258")
def test_persist_notification_increments_cache_for_international_sms_if_the_cache_does_not_exist(
    notify_api, notify_db_session, mocker
):
    service = create_service()
    template = create_template(service=service, template_type=SMS_TYPE)
    api_key = create_api_key(service=service)
    mocker.patch("app.notifications.process_notifications.redis_store.get", return_value=None)
    mock_set = mocker.patch("app.notifications.process_notifications.redis_store.set")
    with set_config(notify_api, "REDIS_ENABLED", True):
        persist_notification(
            template_id=template.id,
            template_version=template.version,
            recipient={
                "unformatted_recipient": "+48697894064",
                "normalised_to": "48697894064",
                "international": True,
                "phone_prefix": "48",
                "rate_multiplier": 2,
            },
            service=template.service,
            personalisation={},
            notification_type=SMS_TYPE,
            api_key_id=api_key.id,
            key_type=api_key.key_type,
            reference="ref2",
        )

        assert mock_set.call_args_list == [
            mocker.call(f"{service.id}-sms-2016-01-01-count", 1, ex=86400),
            mocker.call(f"{service.id}-international_sms-2016-01-01-count", 1, ex=86400),
        ]


@pytest.mark.parametrize(
    ("requested_queue, notification_type, key_type, expected_queue, expected_task"),
    [
        (None, SMS_TYPE, "normal", "send-sms-tasks", "provider_tasks.deliver_sms"),
        (None, EMAIL_TYPE, "normal", "send-email-tasks", "provider_tasks.deliver_email"),
        (None, SMS_TYPE, "team", "send-sms-tasks", "provider_tasks.deliver_sms"),
        (
            None,
            LETTER_TYPE,
            "normal",
            "create-letters-pdf-tasks",
            "letters_pdf_tasks.get_pdf_for_templated_letter",
        ),
        (None, SMS_TYPE, "test", "research-mode-tasks", "provider_tasks.deliver_sms"),
        (
            "notify-internal-tasks",
            SMS_TYPE,
            "normal",
            "notify-internal-tasks",
            "provider_tasks.deliver_sms",
        ),
        (
            "notify-internal-tasks",
            EMAIL_TYPE,
            "normal",
            "notify-internal-tasks",
            "provider_tasks.deliver_email",
        ),
        (
            "notify-internal-tasks",
            SMS_TYPE,
            "test",
            "research-mode-tasks",
            "provider_tasks.deliver_sms",
        ),
    ],
)
def test_send_notification_to_queue(
    notify_db_session,
    requested_queue,
    notification_type,
    key_type,
    expected_queue,
    expected_task,
    mocker,
):
    mocked = mocker.patch(f"app.celery.{expected_task}.apply_async")
    Notification = namedtuple("Notification", ["id", "key_type", "notification_type", "created_at"])
    notification = Notification(
        id=uuid.uuid4(),
        key_type=key_type,
        notification_type=notification_type,
        created_at=datetime.datetime(2016, 11, 11, 16, 8, 18),
    )

    send_notification_to_queue(notification=notification, queue=requested_queue)

    mocked.assert_called_once_with([str(notification.id)], queue=expected_queue)


def test_send_notification_to_queue_throws_exception_deletes_notification(sample_notification, mocker):
    mocked = mocker.patch(
        "app.celery.provider_tasks.deliver_sms.apply_async",
        side_effect=Boto3Error("EXPECTED"),
    )
    with pytest.raises(Boto3Error):
        send_notification_to_queue(sample_notification)
    mocked.assert_called_once_with([str(sample_notification.id)], queue="send-sms-tasks")

    assert Notification.query.count() == 0
    assert NotificationHistory.query.count() == 0


@pytest.mark.parametrize(
    "to_address, notification_type, expected",
    [
        ("+447700900000", SMS_TYPE, True),
        ("+447700900111", SMS_TYPE, True),
        ("+447700900222", SMS_TYPE, True),
        ("07700900000", SMS_TYPE, True),
        ("7700900111", SMS_TYPE, True),
        ("simulate-delivered@notifications.service.gov.uk", EMAIL_TYPE, True),
        ("simulate-delivered-2@notifications.service.gov.uk", EMAIL_TYPE, True),
        ("simulate-delivered-3@notifications.service.gov.uk", EMAIL_TYPE, True),
        ("07515896969", SMS_TYPE, False),
        ("valid_email@test.com", EMAIL_TYPE, False),
    ],
)
def test_simulated_recipient(notify_api, to_address, notification_type, expected):
    """
    The values where the expected = 'research-mode' are listed in the config['SIMULATED_EMAIL_ADDRESSES']
    and config['SIMULATED_SMS_NUMBERS']. These values should result in using the research mode queue.
    SIMULATED_EMAIL_ADDRESSES = (
        'simulate-delivered@notifications.service.gov.uk',
        'simulate-delivered-2@notifications.service.gov.uk',
        'simulate-delivered-2@notifications.service.gov.uk'
    )
    SIMULATED_SMS_NUMBERS = ('+447700900000', '+447700900111', '+447700900222')
    """
    formatted_address = None

    if notification_type == EMAIL_TYPE:
        formatted_address = validate_and_format_email_address(to_address)
    else:
        formatted_address = parse_and_format_phone_number(to_address)

    is_simulated_address = simulated_recipient(formatted_address, notification_type)

    assert is_simulated_address == expected


def test_persist_notification_with_international_info_does_not_store_for_email(sample_job, sample_api_key):
    persist_notification(
        template_id=sample_job.template.id,
        template_version=sample_job.template.version,
        recipient="foo@bar.com",
        service=sample_job.service,
        personalisation=None,
        notification_type=EMAIL_TYPE,
        api_key_id=sample_api_key.id,
        key_type=sample_api_key.key_type,
        job_id=sample_job.id,
        job_row_number=10,
        client_reference="ref from client",
    )
    persisted_notification = Notification.query.all()[0]

    assert persisted_notification.international is False
    assert persisted_notification.phone_prefix is None
    assert persisted_notification.rate_multiplier is None


@pytest.mark.parametrize(
    "recipient, expected_recipient_normalised",
    [("FOO@bar.com", "foo@bar.com"), ("BAR@foo.com", "bar@foo.com")],
)
def test_persist_email_notification_stores_normalised_email(
    sample_job, sample_api_key, recipient, expected_recipient_normalised
):
    persist_notification(
        template_id=sample_job.template.id,
        template_version=sample_job.template.version,
        recipient=recipient,
        service=sample_job.service,
        personalisation=None,
        notification_type=EMAIL_TYPE,
        api_key_id=sample_api_key.id,
        key_type=sample_api_key.key_type,
        job_id=sample_job.id,
    )
    persisted_notification = Notification.query.all()[0]

    assert persisted_notification.to == recipient
    assert persisted_notification.normalised_to == expected_recipient_normalised


@pytest.mark.parametrize(
    "postage_argument, template_postage, expected_postage",
    [
        ("second", "first", "second"),
        ("first", "first", "first"),
        ("first", "second", "first"),
        ("economy", "first", "economy"),
        ("economy", "second", "economy"),
    ],
)
def test_persist_letter_notification_finds_correct_postage(
    mocker,
    postage_argument,
    template_postage,
    expected_postage,
    sample_service_full_permissions,
    sample_api_key,
):
    template = create_template(
        sample_service_full_permissions,
        template_type=LETTER_TYPE,
        postage=template_postage,
    )
    mocker.patch("app.dao.templates_dao.dao_get_template_by_id", return_value=template)
    persist_notification(
        template_id=template.id,
        template_version=template.version,
        recipient="Jane Doe, 10 Downing Street, London",
        service=sample_service_full_permissions,
        personalisation=None,
        notification_type=LETTER_TYPE,
        api_key_id=sample_api_key.id,
        key_type=sample_api_key.key_type,
        postage=postage_argument,
    )
    persisted_notification = Notification.query.all()[0]

    assert persisted_notification.postage == expected_postage


def test_persist_notification_with_billable_units_stores_correct_info(notify_db_session, mocker):
    service = create_service(service_permissions=[LETTER_TYPE])
    template = create_template(service, template_type=LETTER_TYPE)
    mocker.patch("app.dao.templates_dao.dao_get_template_by_id", return_value=template)
    persist_notification(
        template_id=template.id,
        template_version=template.version,
        recipient="123 Main Street",
        service=template.service,
        personalisation=None,
        notification_type=template.template_type,
        api_key_id=None,
        key_type="normal",
        billable_units=3,
    )
    persisted_notification = Notification.query.all()[0]

    assert persisted_notification.billable_units == 3


@pytest.mark.parametrize("postage", ["europe", "rest-of-world"])
def test_persist_notification_for_international_letter(sample_letter_template, postage):
    notification = persist_notification(
        template_id=sample_letter_template.id,
        template_version=sample_letter_template.version,
        recipient="123 Main Street",
        service=sample_letter_template.service,
        personalisation=None,
        notification_type=sample_letter_template.template_type,
        api_key_id=None,
        key_type="normal",
        billable_units=3,
        postage=postage,
    )
    persisted_notification = Notification.query.get(notification.id)
    assert persisted_notification.postage == postage
    assert persisted_notification.international


@pytest.mark.parametrize(
    "unsubscribe_link",
    ["https://please-unsubscribe-me.com/unsubscribe", None],
)
def test_persist_notification_when_template_has_unsubscribe_link_is_false(unsubscribe_link, sample_job):
    service = create_service(service_name="321 Service")
    template = create_template(service=service, has_unsubscribe_link=False, template_type=EMAIL_TYPE)
    sample_job.template = template
    sample_job.service = template.service
    recipient = "foo@bar.com"

    persist_notification(
        notification_id=uuid.uuid4(),
        template_id=sample_job.template.id,
        template_version=sample_job.template.version,
        template_has_unsubscribe_link=sample_job.template.has_unsubscribe_link,
        recipient=recipient,
        service=sample_job.service,
        personalisation=None,
        notification_type=EMAIL_TYPE,
        unsubscribe_link=unsubscribe_link,
        job_id=sample_job.id,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL,
    )

    persisted_notification = Notification.query.first()
    assert persisted_notification.unsubscribe_link == unsubscribe_link


@pytest.mark.parametrize(
    "unsubscribe_link, expected_unsubscribe_link",
    [
        (
            "https://please-unsubscribe-me.com/unsubscribe",
            "https://please-unsubscribe-me.com/unsubscribe",
        ),
        # We don’t persist template-level unsubscribe links – they are generated at time of sending
        (None, None),
    ],
)
def test_persist_notification_when_template_has_unsubscribe_link_is_true(
    unsubscribe_link, sample_service, expected_unsubscribe_link
):
    """
    Tests that if template.has_unsubscribe_link is True that an unsubscribe link is generated by persist_notification
    only if one hasn't already been provided.
    """

    template = create_template(
        template_name="Subscription Template",
        has_unsubscribe_link=True,
        service=sample_service,
        template_type=EMAIL_TYPE,
    )
    job = create_job(template=template)

    recipient = "foo@bar.com"

    persist_notification(
        notification_id=uuid.uuid4(),
        template_id=job.template.id,
        template_version=job.template.version,
        template_has_unsubscribe_link=job.template.has_unsubscribe_link,
        recipient=recipient,
        service=job.service,
        personalisation=None,
        notification_type=EMAIL_TYPE,
        unsubscribe_link=unsubscribe_link,
        job_id=job.id,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL,
    )

    persisted_notification = Notification.query.first()
    assert persisted_notification.unsubscribe_link == expected_unsubscribe_link
