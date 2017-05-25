import uuid

import pytest
from flask import json, current_app

from app.models import Notification
from app.v2.errors import RateLimitError
from tests import create_authorization_header
from tests.app.conftest import sample_template as create_sample_template, sample_service


@pytest.mark.parametrize("reference", [None, "reference_from_client"])
def test_post_sms_notification_returns_201(notify_api, sample_template_with_placeholders, mocker, reference):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
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
            assert mocked.called


@pytest.mark.parametrize("notification_type, key_send_to, send_to",
                         [("sms", "phone_number", "+447700900855"),
                          ("email", "email_address", "sample@email.com")])
def test_post_sms_notification_returns_404_and_missing_template(client, sample_service,
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


@pytest.mark.parametrize("notification_type, key_send_to, send_to",
                         [("sms", "phone_number", "+447700900855"),
                          ("email", "email_address", "sample@email.com")])
def test_post_notification_returns_403_and_well_formed_auth_error(client, sample_template,
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
    assert error_resp['errors'] == [{'error': 'ValidationError',
                                     'message': "template_id is a required property"
                                     }]


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
    notification = Notification.query.first()
    assert resp_json['id'] == str(notification.id)
    assert resp_json['reference'] == reference
    assert notification.reference is None
    assert resp_json['content']['body'] == sample_email_template_with_placeholders.content \
        .replace('((name))', 'Bob').replace('GOV.UK', u'GOV.\u200bUK')
    assert resp_json['content']['subject'] == sample_email_template_with_placeholders.subject \
        .replace('((name))', 'Bob')
    assert resp_json['content']['from_email'] == sample_email_template_with_placeholders.service.email_from
    assert 'v2/notifications/{}'.format(notification.id) in resp_json['uri']
    assert resp_json['template']['id'] == str(sample_email_template_with_placeholders.id)
    assert resp_json['template']['version'] == sample_email_template_with_placeholders.version
    assert 'services/{}/templates/{}'.format(str(sample_email_template_with_placeholders.service_id),
                                             str(sample_email_template_with_placeholders.id)) \
           in resp_json['template']['uri']
    assert mocked.called


@pytest.mark.parametrize('recipient, notification_type', [
    ('simulate-delivered@notifications.service.gov.uk', 'email'),
    ('simulate-delivered-2@notifications.service.gov.uk', 'email'),
    ('simulate-delivered-3@notifications.service.gov.uk', 'email'),
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


def test_post_sms_notification_returns_400_if_not_allowed_to_send_int_sms(client, sample_service, sample_template):
    data = {
        'phone_number': '20-12-1234-1234',
        'template_id': sample_template.id
    }
    auth_header = create_authorization_header(service_id=sample_service.id)

    response = client.post(
        path='/v2/notifications/sms',
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 400
    assert response.headers['Content-type'] == 'application/json'

    error_json = json.loads(response.get_data(as_text=True))
    assert error_json['status_code'] == 400
    assert error_json['errors'] == [
        {"error": "BadRequestError", "message": 'Cannot send to international mobile numbers'}
    ]


def test_post_sms_notification_returns_201_if_allowed_to_send_int_sms(notify_db, notify_db_session, client, mocker):

    service = sample_service(notify_db, notify_db_session, can_send_international_sms=True)
    template = create_sample_template(notify_db, notify_db_session, service=service)

    mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')

    data = {
        'phone_number': '20-12-1234-1234',
        'template_id': template.id
    }
    auth_header = create_authorization_header(service_id=service.id)

    response = client.post(
        path='/v2/notifications/sms',
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])

    print(json.loads(response.get_data(as_text=True)))
    assert response.status_code == 201
    assert response.headers['Content-type'] == 'application/json'


def test_post_sms_should_persist_supplied_sms_number(notify_api, sample_template_with_placeholders, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
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
