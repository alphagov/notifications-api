import pytest
from flask import current_app

from app.constants import EMAIL_TYPE, MANAGE_SETTINGS, SMS_TYPE
from app.dao.services_dao import dao_add_user_to_service, dao_fetch_active_users_for_service
from app.models import Notification
from app.service.sender import notify_user_if_manage_settings_permission_granted, send_notification_to_service_users
from tests.app.db import create_service, create_template, create_user


@pytest.mark.parametrize("notification_type", [EMAIL_TYPE, SMS_TYPE])
def test_send_notification_to_service_users_persists_notifications_correctly(
    notify_service, notification_type, sample_service, mocker
):
    mocker.patch("app.service.sender.send_notification_to_queue")

    user = sample_service.users[0]
    template = create_template(sample_service, template_type=notification_type)
    active_users = dao_fetch_active_users_for_service(sample_service.id)
    send_notification_to_service_users(template_id=template.id, user_list=active_users)
    to = user.email_address if notification_type == EMAIL_TYPE else user.mobile_number

    notification = Notification.query.one()

    assert Notification.query.count() == 1
    assert notification.to == to
    assert str(notification.service_id) == current_app.config["NOTIFY_SERVICE_ID"]
    assert notification.template.id == template.id
    assert notification.template.template_type == notification_type
    assert notification.notification_type == notification_type
    assert notification.reply_to_text == notify_service.get_default_reply_to_email_address()


def test_send_notification_to_service_users_sends_to_queue(notify_service, sample_service, mocker):
    send_mock = mocker.patch("app.service.sender.send_notification_to_queue")

    template = create_template(sample_service, template_type=EMAIL_TYPE)
    active_users = dao_fetch_active_users_for_service(sample_service.id)
    send_notification_to_service_users(template_id=template.id, user_list=active_users)

    assert send_mock.called
    assert send_mock.call_count == 1


def test_send_notification_to_service_users_includes_user_fields_in_personalisation(
    notify_service, sample_service, mocker
):
    persist_mock = mocker.patch("app.service.sender.persist_notification")
    mocker.patch("app.service.sender.send_notification_to_queue")

    user = sample_service.users[0]

    template = create_template(sample_service, template_type=EMAIL_TYPE)
    active_users = dao_fetch_active_users_for_service(sample_service.id)
    send_notification_to_service_users(
        template_id=template.id, user_list=active_users, include_user_fields=["name", "email_address", "state"]
    )

    persist_call = persist_mock.call_args_list[0][1]

    assert len(persist_mock.call_args_list) == 1
    assert persist_call["personalisation"] == {
        "name": user.name,
        "email_address": user.email_address,
        "state": user.state,
    }


def test_send_notification_to_service_users_sends_to_specified_user_list_only(notify_service, mocker):
    mocker.patch("app.service.sender.send_notification_to_queue")

    first_active_user = create_user(email="foo@bar.com", state="active")
    second_active_user = create_user(email="foo1@bar.com", state="active")
    pending_user = create_user(email="foo2@bar.com", state="pending")
    service = create_service(user=first_active_user)
    dao_add_user_to_service(service, second_active_user)
    dao_add_user_to_service(service, pending_user)
    template = create_template(service, template_type=EMAIL_TYPE)
    active_users = dao_fetch_active_users_for_service(service.id)

    send_notification_to_service_users(
        template_id=template.id,
        user_list=active_users,
    )
    notifications = Notification.query.all()
    notifications_recipients = [notification.to for notification in notifications]

    assert Notification.query.count() == 2
    assert pending_user.email_address not in notifications_recipients
    assert first_active_user.email_address in notifications_recipients
    assert second_active_user.email_address in notifications_recipients


@pytest.mark.parametrize(
    "service_restricted,service_active",
    [
        (True, True),
        (True, False),
        (False, False),
    ],
)
def test_notify_user_if_manage_settings_permission_granted_does_nothing_if_service_not_live_or_active(
    sample_user,
    service_restricted,
    service_active,
    mocker,
):
    mock_send_email = mocker.patch("app.service.sender.send_notification_to_service_users")

    service = create_service(
        restricted=service_restricted,
        active=service_active,
    )
    notify_user_if_manage_settings_permission_granted(
        service, sample_user, old_permissions=[], new_permissions=[MANAGE_SETTINGS]
    )

    assert not mock_send_email.called


def test_notify_user_if_manage_settings_permission_granted_does_nothing_if_user_does_not_belong_to_service(
    sample_user,
    mocker,
):
    mock_send_email = mocker.patch("app.service.sender.send_notification_to_service_users")

    service = create_service()

    assert sample_user not in service.users

    notify_user_if_manage_settings_permission_granted(
        service, sample_user, old_permissions=[], new_permissions=[MANAGE_SETTINGS]
    )

    assert not mock_send_email.called


@pytest.mark.parametrize(
    "old_permissions,new_permissions",
    [
        ([], []),
        (["send_emails", "send_letters", "send_texts"], []),
        (["manage_settings"], []),
        (["manage_api_keys"], ["view_activity"]),
        (["manage_settings", "manage_api_keys"], ["manage_settings", "view_activity"]),
    ],
)
def test_notify_user_if_manage_settings_permission_granted_when_email_is_not_sent(
    sample_user,
    old_permissions,
    new_permissions,
    mocker,
):
    mock_send_email = mocker.patch("app.service.sender.send_notification_to_service_users")

    service = create_service(
        user=sample_user,
        restricted=False,
        active=True,
    )

    notify_user_if_manage_settings_permission_granted(
        service,
        sample_user,
        old_permissions=old_permissions,
        new_permissions=new_permissions,
    )

    assert not mock_send_email.called


@pytest.mark.parametrize(
    "old_permissions,new_permissions",
    [
        ([], ["manage_settings", "send_emails", "send_texts", "send_letters"]),
        (["send_emails", "send_texts", "send_letters"], ["manage_settings"]),
        (["view_activity"], ["manage_settings", "manage_api_keys", "view_activity"]),
    ],
)
def test_notify_user_if_manage_settings_permission_granted_when_email_is_sent(
    sample_user,
    old_permissions,
    new_permissions,
    mocker,
):
    mock_send_email = mocker.patch("app.service.sender.send_notification_to_service_users")

    service = create_service(
        user=sample_user,
        restricted=False,
        active=True,
    )

    notify_user_if_manage_settings_permission_granted(
        service=service,
        user=sample_user,
        old_permissions=old_permissions,
        new_permissions=new_permissions,
    )

    mock_send_email.assert_called_once_with(
        template_id=current_app.config["MANAGING_YOUR_SERVICE_TEMPLATE_ID"],
        user_list=[sample_user],
        personalisation={"service_name": "Sample service"},
        include_user_fields=["name"],
    )
