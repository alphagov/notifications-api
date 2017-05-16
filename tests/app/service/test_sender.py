import pytest

from flask import current_app

from app.dao.services_dao import dao_add_user_to_service
from app.models import Notification, EMAIL_TYPE, SMS_TYPE
from app.service.sender import send_notification_to_service_users

from tests.app.conftest import (
    notify_service as create_notify_service,
    sample_service as create_sample_service
)
from tests.app.db import create_template, create_user


@pytest.mark.parametrize('notification_type', [
    EMAIL_TYPE,
    SMS_TYPE
])
def test_send_notification_to_service_users_persists_notifications_correctly(
    notify_db,
    notify_db_session,
    notification_type,
    sample_user,
    mocker
):
    mocker.patch('app.service.sender.send_notification_to_queue')

    create_notify_service(notify_db, notify_db_session)
    service = create_sample_service(notify_db, notify_db_session, user=sample_user)
    template = create_template(service, template_type=notification_type)
    send_notification_to_service_users(service_id=service.id, template_id=template.id)
    to = sample_user.email_address if notification_type == EMAIL_TYPE else sample_user.mobile_number

    notification = Notification.query.one()

    assert Notification.query.count() == 1
    assert notification.to == to
    assert str(notification.service_id) == current_app.config['NOTIFY_SERVICE_ID']
    assert notification.template.id == template.id
    assert notification.template.template_type == notification_type
    assert notification.notification_type == notification_type


def test_send_notification_to_service_users_sends_to_queue(
    notify_db,
    notify_db_session,
    sample_user,
    mocker
):
    send_mock = mocker.patch('app.service.sender.send_notification_to_queue')

    create_notify_service(notify_db, notify_db_session)
    service = create_sample_service(notify_db, notify_db_session, user=sample_user)
    template = create_template(service, template_type=EMAIL_TYPE)
    send_notification_to_service_users(service_id=service.id, template_id=template.id)

    assert send_mock.called
    assert send_mock.call_count == 1


def test_send_notification_to_service_users_includes_user_fields_in_personalisation(
    notify_db,
    notify_db_session,
    sample_user,
    mocker
):
    persist_mock = mocker.patch('app.service.sender.persist_notification')
    mocker.patch('app.service.sender.send_notification_to_queue')

    create_notify_service(notify_db, notify_db_session)
    service = create_sample_service(notify_db, notify_db_session, user=sample_user)
    template = create_template(service, template_type=EMAIL_TYPE)
    send_notification_to_service_users(
        service_id=service.id,
        template_id=template.id,
        include_user_fields=['name', 'email_address', 'state']
    )

    persist_call = persist_mock.call_args_list[0][1]

    assert len(persist_mock.call_args_list) == 1
    assert persist_call['personalisation'] == {
        'name': sample_user.name,
        'email_address': sample_user.email_address,
        'state': sample_user.state,
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
    service = create_sample_service(notify_db, notify_db_session, user=first_active_user)
    dao_add_user_to_service(service, second_active_user)
    dao_add_user_to_service(service, pending_user)
    template = create_template(service, template_type=EMAIL_TYPE)

    send_notification_to_service_users(service_id=service.id, template_id=template.id)
    notifications = Notification.query.all()

    assert Notification.query.count() == 2

    assert notifications[0].to == first_active_user.email_address
    assert notifications[1].to == second_active_user.email_address
