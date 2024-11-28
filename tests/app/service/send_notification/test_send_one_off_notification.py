import uuid
from unittest.mock import Mock

import pytest
from notifications_utils import SMS_CHAR_COUNT_LIMIT
from notifications_utils.recipient_validation.errors import InvalidPhoneError

from app.constants import (
    EMAIL_TYPE,
    KEY_TYPE_NORMAL,
    LETTER_TYPE,
    MOBILE_TYPE,
    SMS_TYPE,
)
from app.dao.service_guest_list_dao import (
    dao_add_and_commit_guest_list_contacts,
)
from app.models import Notification, ServiceGuestList
from app.service.send_notification import send_one_off_notification
from app.v2.errors import BadRequestError, TooManyRequestsError
from tests.app.db import (
    create_letter_contact,
    create_reply_to_email,
    create_service,
    create_service_sms_sender,
    create_template,
    create_user,
)


@pytest.fixture
def persist_mock(mocker):
    noti = Mock(id=uuid.uuid4())
    return mocker.patch("app.service.send_notification.persist_notification", return_value=noti)


@pytest.fixture
def celery_mock(mocker):
    return mocker.patch("app.service.send_notification.send_notification_to_queue")


def test_send_one_off_notification_calls_celery_correctly(persist_mock, celery_mock, notify_db_session):
    service = create_service()
    template = create_template(service=service)

    service = template.service

    post_data = {"template_id": str(template.id), "to": "07700 900 001", "created_by": str(service.created_by_id)}

    resp = send_one_off_notification(service.id, post_data)

    assert resp == {"id": str(persist_mock.return_value.id)}

    celery_mock.assert_called_once_with(notification=persist_mock.return_value)


def test_send_one_off_notification_calls_persist_correctly_for_sms(persist_mock, celery_mock, notify_db_session):
    service = create_service()
    template = create_template(
        service=service,
        template_type=SMS_TYPE,
        content="Hello (( Name))\nYour thing is due soon",
    )

    post_data = {
        "template_id": str(template.id),
        "to": "07700 900 001",
        "personalisation": {"name": "foo"},
        "created_by": str(service.created_by_id),
    }

    send_one_off_notification(service.id, post_data)

    persist_mock.assert_called_once_with(
        template_id=template.id,
        template_version=template.version,
        recipient=post_data["to"],
        service=template.service,
        personalisation={"name": "foo"},
        notification_type=SMS_TYPE,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL,
        created_by_id=str(service.created_by_id),
        reply_to_text="testing",
        reference=None,
        postage=None,
        client_reference=None,
        template_has_unsubscribe_link=False,
    )


def test_send_one_off_notification_calls_persist_correctly_for_international_sms(
    persist_mock, celery_mock, notify_db_session
):
    service = create_service(service_permissions=["sms", "international_sms"])
    template = create_template(
        service=service,
        template_type=SMS_TYPE,
    )

    post_data = {
        "template_id": str(template.id),
        "to": "+1 555 0100",
        "personalisation": {"name": "foo"},
        "created_by": str(service.created_by_id),
    }

    send_one_off_notification(service.id, post_data)

    assert persist_mock.call_args[1]["recipient"] == "+1 555 0100"


def test_send_one_off_notification_calls_persist_correctly_for_email(persist_mock, celery_mock, notify_db_session):
    service = create_service()
    template = create_template(
        service=service,
        template_type=EMAIL_TYPE,
        subject="Test subject",
        content="Hello (( Name))\nYour thing is due soon",
        has_unsubscribe_link=True,
    )

    post_data = {
        "template_id": str(template.id),
        "to": "test@example.com",
        "personalisation": {"name": "foo"},
        "created_by": str(service.created_by_id),
    }

    send_one_off_notification(service.id, post_data)

    persist_mock.assert_called_once_with(
        template_id=template.id,
        template_version=template.version,
        recipient=post_data["to"],
        service=template.service,
        personalisation={"name": "foo"},
        notification_type=EMAIL_TYPE,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL,
        created_by_id=str(service.created_by_id),
        reply_to_text=None,
        reference=None,
        postage=None,
        client_reference=None,
        template_has_unsubscribe_link=True,
    )


def test_send_one_off_notification_calls_persist_correctly_for_letter(
    mocker, persist_mock, celery_mock, notify_db_session
):
    mocker.patch(
        "app.service.send_notification.create_random_identifier",
        return_value="this-is-random-in-real-life",
    )
    service = create_service()
    template = create_template(
        service=service,
        template_type=LETTER_TYPE,
        postage="first",
        subject="Test subject",
        content="Hello (( Name))\nYour thing is due soon",
    )

    post_data = {
        "template_id": str(template.id),
        "to": "First Last",
        "personalisation": {
            "name": "foo",
            "address_line_1": "First Last",
            "address_line_2": "1 Example Street",
            "postcode": "SW1A 1AA",
        },
        "created_by": str(service.created_by_id),
    }

    send_one_off_notification(service.id, post_data)

    persist_mock.assert_called_once_with(
        template_id=template.id,
        template_version=template.version,
        recipient=post_data["to"],
        service=template.service,
        personalisation=post_data["personalisation"],
        notification_type=LETTER_TYPE,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL,
        created_by_id=str(service.created_by_id),
        reply_to_text=None,
        reference="this-is-random-in-real-life",
        postage="first",
        client_reference=None,
        template_has_unsubscribe_link=False,
    )


def test_send_one_off_notification_raises_if_invalid_recipient(notify_db_session):
    service = create_service()
    template = create_template(service=service)

    post_data = {"template_id": str(template.id), "to": "not a phone number", "created_by": str(service.created_by_id)}

    with pytest.raises(InvalidPhoneError):
        send_one_off_notification(service.id, post_data)


@pytest.mark.parametrize(
    "recipient",
    [
        "07700 900 001",  # not in team or guest_list
        "07700900123",  # in guest_list
        "+447700-900-123",  # in guest_list in different format
    ],
)
def test_send_one_off_notification_raises_if_cant_send_to_recipient(
    notify_db_session,
    recipient,
):
    service = create_service(restricted=True)
    template = create_template(service=service)
    dao_add_and_commit_guest_list_contacts(
        [
            ServiceGuestList.from_string(service.id, MOBILE_TYPE, "07700900123"),
        ]
    )

    post_data = {"template_id": str(template.id), "to": recipient, "created_by": str(service.created_by_id)}

    with pytest.raises(BadRequestError) as e:
        send_one_off_notification(service.id, post_data)

    assert "service is in trial mode" in e.value.message


def test_send_one_off_notification_raises_if_over_limit(notify_db_session, mocker):
    service = create_service(sms_message_limit=0)
    template = create_template(service=service)
    mock_check_message_limit = mocker.patch(
        "app.service.send_notification.check_service_over_daily_message_limit",
        side_effect=TooManyRequestsError(SMS_TYPE, 1),
    )

    post_data = {"template_id": str(template.id), "to": "07700 900 001", "created_by": str(service.created_by_id)}

    with pytest.raises(TooManyRequestsError):
        send_one_off_notification(service.id, post_data)

    assert mock_check_message_limit.call_args_list == [mocker.call(service, "normal", notification_type=SMS_TYPE)]


def test_send_one_off_notification_raises_if_message_too_long(persist_mock, notify_db_session):
    service = create_service()
    template = create_template(service=service, content="Hello (( Name))\nYour thing is due soon")

    post_data = {
        "template_id": str(template.id),
        "to": "07700 900 001",
        "personalisation": {"name": "🚫" * 1000},
        "created_by": str(service.created_by_id),
    }

    with pytest.raises(BadRequestError) as e:
        send_one_off_notification(service.id, post_data)

    assert (
        e.value.message == f"Your message is too long. "
        f"Text messages cannot be longer than {SMS_CHAR_COUNT_LIMIT} characters. "
        f"Your message is {1029} characters long."
    )


def test_send_one_off_notification_fails_if_created_by_other_service(sample_template):
    user_not_in_service = create_user(email="some-other-user@gov.uk")

    post_data = {
        "template_id": str(sample_template.id),
        "to": "07700 900 001",
        "created_by": str(user_not_in_service.id),
    }

    with pytest.raises(BadRequestError) as e:
        send_one_off_notification(sample_template.service_id, post_data)

    assert e.value.message == 'Can’t create notification - Test User is not part of the "Sample service" service'


def test_send_one_off_notification_should_add_email_reply_to_text_for_notification(sample_email_template, celery_mock):
    reply_to_email = create_reply_to_email(sample_email_template.service, "test@test.com")
    data = {
        "to": "ok@ok.com",
        "template_id": str(sample_email_template.id),
        "sender_id": reply_to_email.id,
        "created_by": str(sample_email_template.service.created_by_id),
    }

    notification_id = send_one_off_notification(service_id=sample_email_template.service.id, post_data=data)
    notification = Notification.query.get(notification_id["id"])
    celery_mock.assert_called_once_with(notification=notification)
    assert notification.reply_to_text == reply_to_email.email_address


def test_send_one_off_letter_notification_should_use_template_reply_to_text(sample_letter_template, celery_mock):
    letter_contact = create_letter_contact(sample_letter_template.service, "Edinburgh, ED1 1AA", is_default=False)
    sample_letter_template.reply_to = str(letter_contact.id)

    data = {
        "to": "user@example.com",
        "template_id": str(sample_letter_template.id),
        "personalisation": {
            "name": "foo",
            "address_line_1": "First Last",
            "address_line_2": "1 Example Street",
            "address_line_3": "SW1A 1AA",
        },
        "created_by": str(sample_letter_template.service.created_by_id),
    }

    notification_id = send_one_off_notification(service_id=sample_letter_template.service.id, post_data=data)
    notification = Notification.query.get(notification_id["id"])
    celery_mock.assert_called_once_with(notification=notification)

    assert notification.reply_to_text == "Edinburgh, ED1 1AA"


def test_send_one_off_sms_notification_should_use_sms_sender_reply_to_text(sample_service, celery_mock):
    template = create_template(service=sample_service, template_type=SMS_TYPE)
    sms_sender = create_service_sms_sender(service=sample_service, sms_sender="07123123123", is_default=False)

    data = {
        "to": "07111111111",
        "template_id": str(template.id),
        "created_by": str(sample_service.created_by_id),
        "sender_id": str(sms_sender.id),
    }

    notification_id = send_one_off_notification(service_id=sample_service.id, post_data=data)
    notification = Notification.query.get(notification_id["id"])
    celery_mock.assert_called_once_with(notification=notification)

    assert notification.reply_to_text == "447123123123"


def test_send_one_off_sms_notification_should_use_default_service_reply_to_text(sample_service, celery_mock):
    template = create_template(service=sample_service, template_type=SMS_TYPE)
    sample_service.service_sms_senders[0].is_default = False
    create_service_sms_sender(service=sample_service, sms_sender="07123123456", is_default=True)

    data = {
        "to": "07111111111",
        "template_id": str(template.id),
        "created_by": str(sample_service.created_by_id),
    }

    notification_id = send_one_off_notification(service_id=sample_service.id, post_data=data)
    notification = Notification.query.get(notification_id["id"])
    celery_mock.assert_called_once_with(notification=notification)

    assert notification.reply_to_text == "447123123456"


def test_send_one_off_notification_should_throw_exception_if_reply_to_id_doesnot_exist(sample_email_template):
    data = {
        "to": "ok@ok.com",
        "template_id": str(sample_email_template.id),
        "sender_id": str(uuid.uuid4()),
        "created_by": str(sample_email_template.service.created_by_id),
    }

    with pytest.raises(expected_exception=BadRequestError) as e:
        send_one_off_notification(service_id=sample_email_template.service.id, post_data=data)
    assert e.value.message == "Reply to email address not found"


def test_send_one_off_notification_should_throw_exception_if_sms_sender_id_doesnot_exist(sample_template):
    data = {
        "to": "07700 900 001",
        "template_id": str(sample_template.id),
        "sender_id": str(uuid.uuid4()),
        "created_by": str(sample_template.service.created_by_id),
    }

    with pytest.raises(expected_exception=BadRequestError) as e:
        send_one_off_notification(service_id=sample_template.service.id, post_data=data)
    assert e.value.message == "SMS sender not found"
