import pytest
from flask import current_app

from app.dao.services_dao import dao_add_user_to_service
from app.models import EMAIL_TYPE, SMS_TYPE, Notification
from app.service.sender import send_notification_to_service_users
from tests.app.conftest import notify_service as create_notify_service
from tests.app.db import create_service, create_template, create_user


@pytest.mark.parametrize('notification_type', [
    EMAIL_TYPE,
    SMS_TYPE
])
def test_send_notification_to_service_users_persists_notifications_correctly(
    notify_db,
    notify_db_session,
    notification_type,
    sample_service,
    mocker
):
    mocker.patch('app.service.sender.send_notification_to_queue')

    notify_service, _ = create_notify_service(notify_db, notify_db_session)
    user = sample_service.users[0]
    template = create_template(sample_service, template_type=notification_type)
    send_notification_to_service_users(service_id=sample_service.id, template_id=template.id)
    to = user.email_address if notification_type == EMAIL_TYPE else user.mobile_number

    notification = Notification.query.one()

    assert Notification.query.count() == 1
    assert notification.to == to
    assert str(notification.service_id) == current_app.config['NOTIFY_SERVICE_ID']
    assert notification.template.id == template.id
    assert notification.template.template_type == notification_type
    assert notification.notification_type == notification_type
    assert notification.reply_to_text == notify_service.get_default_reply_to_email_address()


def test_send_notification_to_service_users_sends_to_queue(
    notify_db,
    notify_db_session,
    sample_service,
    mocker
):
    send_mock = mocker.patch('app.service.sender.send_notification_to_queue')

    create_notify_service(notify_db, notify_db_session)
    template = create_template(sample_service, template_type=EMAIL_TYPE)
    send_notification_to_service_users(service_id=sample_service.id, template_id=template.id)

    assert send_mock.called
    assert send_mock.call_count == 1


def test_send_notification_to_service_users_includes_user_fields_in_personalisation(
    notify_db,
    notify_db_session,
    sample_service,
    mocker
):
    persist_mock = mocker.patch('app.service.sender.persist_notification')
    mocker.patch('app.service.sender.send_notification_to_queue')

    create_notify_service(notify_db, notify_db_session)
    user = sample_service.users[0]

    template = create_template(sample_service, template_type=EMAIL_TYPE)
    send_notification_to_service_users(
        service_id=sample_service.id,
        template_id=template.id,
        include_user_fields=['name', 'email_address', 'state']
    )

    persist_call = persist_mock.call_args_list[0][1]

    assert len(persist_mock.call_args_list) == 1
    assert persist_call['personalisation'] == {
        'name': user.name,
        'email_address': user.email_address,
        'state': user.state,
    }


def test_send_notification_to_service_users_sends_to_active_users_only(
    notify_db,
    notify_db_session,
    mocker
):
    mocker.patch('app.service.sender.send_notification_to_queue')

    create_notify_service(notify_db, notify_db_session)

    first_active_user = create_user(email='foo@bar.com', state='active')
    second_active_user = create_user(email='foo1@bar.com', state='active')
    pending_user = create_user(email='foo2@bar.com', state='pending')
    service = create_service(user=first_active_user)
    dao_add_user_to_service(service, second_active_user)
    dao_add_user_to_service(service, pending_user)
    template = create_template(service, template_type=EMAIL_TYPE)

    send_notification_to_service_users(service_id=service.id, template_id=template.id)
    notifications = Notification.query.all()
    notifications_recipients = [notification.to for notification in notifications]

    assert Notification.query.count() == 2
    assert pending_user.email_address not in notifications_recipients
    assert first_active_user.email_address in notifications_recipients
    assert second_active_user.email_address in notifications_recipients
