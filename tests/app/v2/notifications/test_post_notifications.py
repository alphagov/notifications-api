import uuid

import pytest
from freezegun import freeze_time

from app.dao.service_sms_sender_dao import dao_update_service_sms_sender
from app.models import (
    ScheduledNotification,
    SCHEDULE_NOTIFICATIONS,
    EMAIL_TYPE,
    SMS_TYPE
)
from flask import json, current_app

from app.models import Notification
from app.schema_validation import validate
from app.v2.errors import RateLimitError
from app.v2.notifications.notification_schemas import post_sms_response, post_email_response
from tests import create_authorization_header
from tests.app.conftest import (
    sample_template as create_sample_template,
    sample_service,
    sample_template_without_email_permission,
    sample_template_without_sms_permission
)

from tests.app.db import (
    create_service,
    create_template,
    create_reply_to_email,
    create_service_sms_sender,
    create_service_with_inbound_number
)


@pytest.mark.parametrize("reference", [None, "reference_from_client"])
def test_post_sms_notification_returns_201(client, sample_template_with_placeholders, mocker, reference):
    mocked = mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')
    data = {
        'phone_number': '+447700900855',
        'template_id': str(sample_template_with_placeholders.id),
        'personalisation': {' Name': 'Jo'}
    }
    if reference:
        data.update({"reference": reference})
    auth_header = create_authorization_header(service_id=sample_template_with_placeholders.service_id)

    response = client.post(
        path='/v2/notifications/sms',
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])
    assert response.status_code == 201
    resp_json = json.loads(response.get_data(as_text=True))
    assert validate(resp_json, post_sms_response) == resp_json
    notifications = Notification.query.all()
    assert len(notifications) == 1
    notification_id = notifications[0].id
    assert resp_json['id'] == str(notification_id)
    assert resp_json['reference'] == reference
    assert resp_json['content']['body'] == sample_template_with_placeholders.content.replace("(( Name))", "Jo")
    assert resp_json['content']['from_number'] == current_app.config['FROM_NUMBER']
    assert 'v2/notifications/{}'.format(notification_id) in resp_json['uri']
    assert resp_json['template']['id'] == str(sample_template_with_placeholders.id)
    assert resp_json['template']['version'] == sample_template_with_placeholders.version
    assert 'services/{}/templates/{}'.format(sample_template_with_placeholders.service_id,
                                             sample_template_with_placeholders.id) \
           in resp_json['template']['uri']
    assert not resp_json["scheduled_for"]
    assert mocked.called


def test_post_sms_notification_uses_inbound_number_as_sender(client, notify_db_session, mocker):
    service = create_service_with_inbound_number(inbound_number='1')

    template = create_template(service=service, content="Hello (( Name))\nYour thing is due soon")
    mocked = mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')
    data = {
        'phone_number': '+447700900855',
        'template_id': str(template.id),
        'personalisation': {' Name': 'Jo'}
    }
    auth_header = create_authorization_header(service_id=service.id)

    response = client.post(
        path='/v2/notifications/sms',
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])
    assert response.status_code == 201
    resp_json = json.loads(response.get_data(as_text=True))
    assert validate(resp_json, post_sms_response) == resp_json
    notifications = Notification.query.all()
    assert len(notifications) == 1
    notification_id = notifications[0].id
    assert resp_json['id'] == str(notification_id)
    assert resp_json['content']['from_number'] == '1'
    assert notifications[0].reply_to_text == '1'
    mocked.assert_called_once_with([str(notification_id)], queue='send-sms-tasks')


def test_post_sms_notification_uses_inbound_number_reply_to_as_sender(client, notify_db_session, mocker):
    service = create_service_with_inbound_number(inbound_number='07123123123')

    template = create_template(service=service, content="Hello (( Name))\nYour thing is due soon")
    mocked = mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')
    data = {
        'phone_number': '+447700900855',
        'template_id': str(template.id),
        'personalisation': {' Name': 'Jo'}
    }
    auth_header = create_authorization_header(service_id=service.id)

    response = client.post(
        path='/v2/notifications/sms',
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])
    assert response.status_code == 201
    resp_json = json.loads(response.get_data(as_text=True))
    assert validate(resp_json, post_sms_response) == resp_json
    notifications = Notification.query.all()
    assert len(notifications) == 1
    notification_id = notifications[0].id
    assert resp_json['id'] == str(notification_id)
    assert resp_json['content']['from_number'] == '447123123123'
    assert notifications[0].reply_to_text == '447123123123'
    mocked.assert_called_once_with([str(notification_id)], queue='send-sms-tasks')


def test_post_sms_notification_returns_201_with_sms_sender_id(
        client, sample_template_with_placeholders, mocker
):
    sms_sender = create_service_sms_sender(service=sample_template_with_placeholders.service, sms_sender='123456')
    mocked = mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')
    data = {
        'phone_number': '+447700900855',
        'template_id': str(sample_template_with_placeholders.id),
        'personalisation': {' Name': 'Jo'},
        'sms_sender_id': str(sms_sender.id)
    }
    auth_header = create_authorization_header(service_id=sample_template_with_placeholders.service_id)

    response = client.post(
        path='/v2/notifications/sms',
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])
    assert response.status_code == 201
    resp_json = json.loads(response.get_data(as_text=True))
    assert validate(resp_json, post_sms_response) == resp_json
    assert resp_json['content']['from_number'] == sms_sender.sms_sender
    notifications = Notification.query.all()
    assert len(notifications) == 1
    assert notifications[0].reply_to_text == sms_sender.sms_sender
    mocked.assert_called_once_with([resp_json['id']], queue='send-sms-tasks')


def test_post_sms_notification_uses_sms_sender_id_reply_to(
        client, sample_template_with_placeholders, mocker
):
    sms_sender = create_service_sms_sender(service=sample_template_with_placeholders.service, sms_sender='07123123123')
    mocked = mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')
    data = {
        'phone_number': '+447700900855',
        'template_id': str(sample_template_with_placeholders.id),
        'personalisation': {' Name': 'Jo'},
        'sms_sender_id': str(sms_sender.id)
    }
    auth_header = create_authorization_header(service_id=sample_template_with_placeholders.service_id)

    response = client.post(
        path='/v2/notifications/sms',
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])
    assert response.status_code == 201
    resp_json = json.loads(response.get_data(as_text=True))
    assert validate(resp_json, post_sms_response) == resp_json
    assert resp_json['content']['from_number'] == '447123123123'
    notifications = Notification.query.all()
    assert len(notifications) == 1
    assert notifications[0].reply_to_text == '447123123123'
    mocked.assert_called_once_with([resp_json['id']], queue='send-sms-tasks')


def test_notification_reply_to_text_is_original_value_if_sender_is_changed_after_post_notification(
        client, sample_template, mocker
):
    sms_sender = create_service_sms_sender(service=sample_template.service, sms_sender='123456', is_default=False)
    mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')
    data = {
        'phone_number': '+447700900855',
        'template_id': str(sample_template.id),
        'sms_sender_id': str(sms_sender.id)
    }
    auth_header = create_authorization_header(service_id=sample_template.service_id)

    response = client.post(
        path='/v2/notifications/sms',
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])

    dao_update_service_sms_sender(service_id=sample_template.service_id,
                                  service_sms_sender_id=sms_sender.id,
                                  is_default=sms_sender.is_default,
                                  sms_sender='updated')

    assert response.status_code == 201
    notifications = Notification.query.all()
    assert len(notifications) == 1
    assert notifications[0].reply_to_text == '123456'


@pytest.mark.parametrize("notification_type, key_send_to, send_to",
                         [("sms", "phone_number", "+447700900855"),
                          ("email", "email_address", "sample@email.com")])
def test_post_notification_returns_400_and_missing_template(client, sample_service,
                                                            notification_type, key_send_to, send_to):
    data = {
        key_send_to: send_to,
        'template_id': str(uuid.uuid4())
    }
    auth_header = create_authorization_header(service_id=sample_service.id)

    response = client.post(
        path='/v2/notifications/{}'.format(notification_type),
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 400
    assert response.headers['Content-type'] == 'application/json'

    error_json = json.loads(response.get_data(as_text=True))
    assert error_json['status_code'] == 400
    assert error_json['errors'] == [{"error": "BadRequestError",
                                     "message": 'Template not found'}]


@pytest.mark.parametrize("notification_type, key_send_to, send_to", [
    ("sms", "phone_number", "+447700900855"),
    ("email", "email_address", "sample@email.com"),
    ("letter", "personalisation", {"address_line_1": "The queen", "postcode": "SW1 1AA"})
])
def test_post_notification_returns_401_and_well_formed_auth_error(client, sample_template,
                                                                  notification_type, key_send_to, send_to):
    data = {
        key_send_to: send_to,
        'template_id': str(sample_template.id)
    }

    response = client.post(
        path='/v2/notifications/{}'.format(notification_type),
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json')])

    assert response.status_code == 401
    assert response.headers['Content-type'] == 'application/json'
    error_resp = json.loads(response.get_data(as_text=True))
    assert error_resp['status_code'] == 401
    assert error_resp['errors'] == [{'error': "AuthError",
                                     'message': 'Unauthorized, authentication token must be provided'}]


@pytest.mark.parametrize("notification_type, key_send_to, send_to",
                         [("sms", "phone_number", "+447700900855"),
                          ("email", "email_address", "sample@email.com")])
def test_notification_returns_400_and_for_schema_problems(client, sample_template, notification_type, key_send_to,
                                                          send_to):
    data = {
        key_send_to: send_to,
        'template': str(sample_template.id)
    }
    auth_header = create_authorization_header(service_id=sample_template.service_id)

    response = client.post(
        path='/v2/notifications/{}'.format(notification_type),
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 400
    assert response.headers['Content-type'] == 'application/json'
    error_resp = json.loads(response.get_data(as_text=True))
    assert error_resp['status_code'] == 400
    assert {'error': 'ValidationError',
            'message': "template_id is a required property"
            } in error_resp['errors']
    assert {'error': 'ValidationError',
            'message':
            'Additional properties are not allowed (template was unexpected)'
            } in error_resp['errors']


@pytest.mark.parametrize("reference", [None, "reference_from_client"])
def test_post_email_notification_returns_201(client, sample_email_template_with_placeholders, mocker, reference):
    mocked = mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    data = {
        "email_address": sample_email_template_with_placeholders.service.users[0].email_address,
        "template_id": sample_email_template_with_placeholders.id,
        "personalisation": {"name": "Bob"}
    }
    if reference:
        data.update({"reference": reference})
    auth_header = create_authorization_header(service_id=sample_email_template_with_placeholders.service_id)
    response = client.post(
        path="v2/notifications/email",
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])
    assert response.status_code == 201
    resp_json = json.loads(response.get_data(as_text=True))
    assert validate(resp_json, post_email_response) == resp_json
    notification = Notification.query.one()
    assert resp_json['id'] == str(notification.id)
    assert resp_json['reference'] == reference
    assert notification.reference is None
    assert notification.reply_to_text is None
    assert resp_json['content']['body'] == sample_email_template_with_placeholders.content \
        .replace('((name))', 'Bob').replace('GOV.UK', u'GOV.\u200bUK')
    assert resp_json['content']['subject'] == sample_email_template_with_placeholders.subject \
        .replace('((name))', 'Bob')
    assert resp_json['content']['from_email'] == "{}@{}".format(
        sample_email_template_with_placeholders.service.email_from, current_app.config['NOTIFY_EMAIL_DOMAIN'])
    assert 'v2/notifications/{}'.format(notification.id) in resp_json['uri']
    assert resp_json['template']['id'] == str(sample_email_template_with_placeholders.id)
    assert resp_json['template']['version'] == sample_email_template_with_placeholders.version
    assert 'services/{}/templates/{}'.format(str(sample_email_template_with_placeholders.service_id),
                                             str(sample_email_template_with_placeholders.id)) \
           in resp_json['template']['uri']
    assert not resp_json["scheduled_for"]
    assert mocked.called


@pytest.mark.parametrize('recipient, notification_type', [
    ('simulate-delivered@notifications.service.gov.uk', EMAIL_TYPE),
    ('simulate-delivered-2@notifications.service.gov.uk', EMAIL_TYPE),
    ('simulate-delivered-3@notifications.service.gov.uk', EMAIL_TYPE),
    ('07700 900000', 'sms'),
    ('07700 900111', 'sms'),
    ('07700 900222', 'sms')
])
def test_should_not_persist_or_send_notification_if_simulated_recipient(
        client,
        recipient,
        notification_type,
        sample_email_template,
        sample_template,
        mocker):
    apply_async = mocker.patch('app.celery.provider_tasks.deliver_{}.apply_async'.format(notification_type))

    if notification_type == 'sms':
        data = {
            'phone_number': recipient,
            'template_id': str(sample_template.id)
        }
    else:
        data = {
            'email_address': recipient,
            'template_id': str(sample_email_template.id)
        }

    auth_header = create_authorization_header(service_id=sample_email_template.service_id)

    response = client.post(
        path='/v2/notifications/{}'.format(notification_type),
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 201
    apply_async.assert_not_called()
    assert json.loads(response.get_data(as_text=True))["id"]
    assert Notification.query.count() == 0


@pytest.mark.parametrize("notification_type, key_send_to, send_to",
                         [("sms", "phone_number", "07700 900 855"),
                          ("email", "email_address", "sample@email.com")])
def test_send_notification_uses_priority_queue_when_template_is_marked_as_priority(client, notify_db,
                                                                                   notify_db_session,
                                                                                   mocker,
                                                                                   notification_type,
                                                                                   key_send_to,
                                                                                   send_to):
    mocker.patch('app.celery.provider_tasks.deliver_{}.apply_async'.format(notification_type))

    sample = create_sample_template(
        notify_db,
        notify_db_session,
        template_type=notification_type,
        process_type='priority'
    )
    mocked = mocker.patch('app.celery.provider_tasks.deliver_{}.apply_async'.format(notification_type))

    data = {
        key_send_to: send_to,
        'template_id': str(sample.id)
    }

    auth_header = create_authorization_header(service_id=sample.service_id)

    response = client.post(
        path='/v2/notifications/{}'.format(notification_type),
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])

    notification_id = json.loads(response.data)['id']

    assert response.status_code == 201
    mocked.assert_called_once_with([notification_id], queue='priority-tasks')


@pytest.mark.parametrize(
    "notification_type, key_send_to, send_to",
    [("sms", "phone_number", "07700 900 855"), ("email", "email_address", "sample@email.com")]
)
def test_returns_a_429_limit_exceeded_if_rate_limit_exceeded(
        client,
        notify_db,
        notify_db_session,
        mocker,
        notification_type,
        key_send_to,
        send_to
):
    sample = create_sample_template(
        notify_db,
        notify_db_session,
        template_type=notification_type
    )
    persist_mock = mocker.patch('app.v2.notifications.post_notifications.persist_notification')
    deliver_mock = mocker.patch('app.v2.notifications.post_notifications.send_notification_to_queue')
    mocker.patch(
        'app.v2.notifications.post_notifications.check_rate_limiting',
        side_effect=RateLimitError("LIMIT", "INTERVAL", "TYPE"))

    data = {
        key_send_to: send_to,
        'template_id': str(sample.id)
    }

    auth_header = create_authorization_header(service_id=sample.service_id)

    response = client.post(
        path='/v2/notifications/{}'.format(notification_type),
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])

    error = json.loads(response.data)['errors'][0]['error']
    message = json.loads(response.data)['errors'][0]['message']
    status_code = json.loads(response.data)['status_code']
    assert response.status_code == 429
    assert error == 'RateLimitError'
    assert message == 'Exceeded rate limit for key type TYPE of LIMIT requests per INTERVAL seconds'
    assert status_code == 429

    assert not persist_mock.called
    assert not deliver_mock.called


def test_post_sms_notification_returns_400_if_not_allowed_to_send_int_sms(
        client,
        notify_db,
        notify_db_session,
):
    service = sample_service(notify_db, notify_db_session, permissions=[SMS_TYPE])
    template = create_sample_template(notify_db, notify_db_session, service=service)

    data = {
        'phone_number': '20-12-1234-1234',
        'template_id': template.id
    }
    auth_header = create_authorization_header(service_id=service.id)

    response = client.post(
        path='/v2/notifications/sms',
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header]
    )

    assert response.status_code == 400
    assert response.headers['Content-type'] == 'application/json'

    error_json = json.loads(response.get_data(as_text=True))
    assert error_json['status_code'] == 400
    assert error_json['errors'] == [
        {"error": "BadRequestError", "message": 'Cannot send to international mobile numbers'}
    ]


@pytest.mark.parametrize('recipient,label,template_factory,expected_error', [
    ('07700 900000', 'phone_number', sample_template_without_sms_permission, 'Cannot send text messages'),
    ('someone@test.com', 'email_address', sample_template_without_email_permission, 'Cannot send emails')])
def test_post_sms_notification_returns_400_if_not_allowed_to_send_notification(
        client, template_factory, recipient, label, expected_error, notify_db, notify_db_session):
    sample_template_without_permission = template_factory(notify_db, notify_db_session)
    data = {
        label: recipient,
        'template_id': sample_template_without_permission.id
    }
    auth_header = create_authorization_header(service_id=sample_template_without_permission.service.id)

    response = client.post(
        path='/v2/notifications/{}'.format(sample_template_without_permission.template_type),
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 400
    assert response.headers['Content-type'] == 'application/json'

    error_json = json.loads(response.get_data(as_text=True))
    assert error_json['status_code'] == 400
    assert error_json['errors'] == [
        {"error": "BadRequestError", "message": expected_error}
    ]


def test_post_sms_notification_returns_201_if_allowed_to_send_int_sms(
        sample_service,
        sample_template,
        client,
        mocker,
):
    mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')

    data = {
        'phone_number': '20-12-1234-1234',
        'template_id': sample_template.id
    }
    auth_header = create_authorization_header(service_id=sample_service.id)

    response = client.post(
        path='/v2/notifications/sms',
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 201
    assert response.headers['Content-type'] == 'application/json'


def test_post_sms_should_persist_supplied_sms_number(client, sample_template_with_placeholders, mocker):
    mocked = mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')
    data = {
        'phone_number': '+(44) 77009-00855',
        'template_id': str(sample_template_with_placeholders.id),
        'personalisation': {' Name': 'Jo'}
    }

    auth_header = create_authorization_header(service_id=sample_template_with_placeholders.service_id)

    response = client.post(
        path='/v2/notifications/sms',
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])
    assert response.status_code == 201
    resp_json = json.loads(response.get_data(as_text=True))
    notifications = Notification.query.all()
    assert len(notifications) == 1
    notification_id = notifications[0].id
    assert '+(44) 77009-00855' == notifications[0].to
    assert resp_json['id'] == str(notification_id)
    assert mocked.called


@pytest.mark.parametrize("notification_type, key_send_to, send_to",
                         [("sms", "phone_number", "07700 900 855"),
                          ("email", "email_address", "sample@email.com")])
@freeze_time("2017-05-14 14:00:00")
def test_post_notification_with_scheduled_for(client, notify_db, notify_db_session,
                                              notification_type, key_send_to, send_to):
    service = create_service(service_name=str(uuid.uuid4()),
                             service_permissions=[EMAIL_TYPE, SMS_TYPE, SCHEDULE_NOTIFICATIONS])
    template = create_template(service=service, template_type=notification_type)
    data = {
        key_send_to: send_to,
        'template_id': str(template.id) if notification_type == EMAIL_TYPE else str(template.id),
        'scheduled_for': '2017-05-14 14:15'
    }
    auth_header = create_authorization_header(service_id=service.id)

    response = client.post('/v2/notifications/{}'.format(notification_type),
                           data=json.dumps(data),
                           headers=[('Content-Type', 'application/json'), auth_header])
    assert response.status_code == 201
    resp_json = json.loads(response.get_data(as_text=True))
    scheduled_notification = ScheduledNotification.query.filter_by(notification_id=resp_json["id"]).all()
    assert len(scheduled_notification) == 1
    assert resp_json["id"] == str(scheduled_notification[0].notification_id)
    assert resp_json["scheduled_for"] == '2017-05-14 14:15'


@pytest.mark.parametrize("notification_type, key_send_to, send_to",
                         [("sms", "phone_number", "07700 900 855"),
                          ("email", "email_address", "sample@email.com")])
@freeze_time("2017-05-14 14:00:00")
def test_post_notification_raises_bad_request_if_service_not_invited_to_schedule(
        client, sample_template, sample_email_template, notification_type, key_send_to, send_to):
    data = {
        key_send_to: send_to,
        'template_id': str(sample_email_template.id) if notification_type == EMAIL_TYPE else str(sample_template.id),
        'scheduled_for': '2017-05-14 14:15'
    }
    auth_header = create_authorization_header(service_id=sample_template.service_id)

    response = client.post('/v2/notifications/{}'.format(notification_type),
                           data=json.dumps(data),
                           headers=[('Content-Type', 'application/json'), auth_header])
    assert response.status_code == 400
    error_json = json.loads(response.get_data(as_text=True))
    assert error_json['errors'] == [
        {"error": "BadRequestError", "message": 'Cannot schedule notifications (this feature is invite-only)'}]


def test_post_notification_raises_bad_request_if_not_valid_notification_type(client, sample_service):
    auth_header = create_authorization_header(service_id=sample_service.id)
    response = client.post(
        '/v2/notifications/foo',
        data='{}',
        headers=[('Content-Type', 'application/json'), auth_header]
    )
    assert response.status_code == 404
    error_json = json.loads(response.get_data(as_text=True))
    assert 'The requested URL was not found on the server.' in error_json['message']


@pytest.mark.parametrize("notification_type",
                         ['sms', 'email'])
def test_post_notification_with_wrong_type_of_sender(
        client,
        sample_template,
        sample_email_template,
        notification_type,
        fake_uuid):
    if notification_type == EMAIL_TYPE:
        template = sample_email_template
        form_label = 'sms_sender_id'
        data = {
            'email_address': 'test@test.com',
            'template_id': str(sample_email_template.id),
            form_label: fake_uuid
        }
    elif notification_type == SMS_TYPE:
        template = sample_template
        form_label = 'email_reply_to_id'
        data = {
            'phone_number': '+447700900855',
            'template_id': str(template.id),
            form_label: fake_uuid
        }
    auth_header = create_authorization_header(service_id=template.service_id)

    response = client.post(
        path='/v2/notifications/{}'.format(notification_type),
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])
    assert response.status_code == 400
    resp_json = json.loads(response.get_data(as_text=True))
    assert 'Additional properties are not allowed ({} was unexpected)'.format(form_label) \
           in resp_json['errors'][0]['message']
    assert 'ValidationError' in resp_json['errors'][0]['error']


def test_post_email_notification_with_valid_reply_to_id_returns_201(client, sample_email_template, mocker):
    reply_to_email = create_reply_to_email(sample_email_template.service, 'test@test.com')
    mocked = mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    data = {
        "email_address": sample_email_template.service.users[0].email_address,
        "template_id": sample_email_template.id,
        'email_reply_to_id': reply_to_email.id
    }
    auth_header = create_authorization_header(service_id=sample_email_template.service_id)
    response = client.post(
        path="v2/notifications/email",
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])
    assert response.status_code == 201
    resp_json = json.loads(response.get_data(as_text=True))
    assert validate(resp_json, post_email_response) == resp_json
    notification = Notification.query.first()
    assert notification.reply_to_text == 'test@test.com'
    assert resp_json['id'] == str(notification.id)
    assert mocked.called

    assert notification.reply_to_text == reply_to_email.email_address


def test_post_email_notification_with_invalid_reply_to_id_returns_400(client, sample_email_template, mocker, fake_uuid):
    mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    data = {
        "email_address": sample_email_template.service.users[0].email_address,
        "template_id": sample_email_template.id,
        'email_reply_to_id': fake_uuid
    }
    auth_header = create_authorization_header(service_id=sample_email_template.service_id)
    response = client.post(
        path="v2/notifications/email",
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])
    assert response.status_code == 400
    resp_json = json.loads(response.get_data(as_text=True))
    assert 'email_reply_to_id {} does not exist in database for service id {}'. \
        format(fake_uuid, sample_email_template.service_id) in resp_json['errors'][0]['message']
    assert 'BadRequestError' in resp_json['errors'][0]['error']
