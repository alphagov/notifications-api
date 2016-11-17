import uuid

import pytest
from flask import json
from app.models import Notification
from tests import create_authorization_header


def test_post_sms_notification_returns_201(notify_api, sample_template, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocked = mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')
            data = {
                'phone_number': '+447700900855',
                'template_id': str(sample_template.id),
                'reference': 'reference_from_client'
            }
            auth_header = create_authorization_header(service_id=sample_template.service_id)

            response = client.post(
                path='/v2/notifications/sms',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            assert response.status_code == 201
            resp_json = json.loads(response.get_data(as_text=True))
            notifications = Notification.query.all()
            assert len(notifications) == 1
            notification_id = notifications[0].id
            assert resp_json['id'] is not None
            assert resp_json['reference'] == 'reference_from_client'
            assert resp_json['content']['body'] == sample_template.content
            assert resp_json['content']['from_number'] == sample_template.service.sms_sender
            assert 'v2/notifications/{}'.format(notification_id) in resp_json['uri']
            assert resp_json['template']['id'] == str(sample_template.id)
            assert resp_json['template']['version'] == sample_template.version
            assert 'v2/templates/{}'.format(sample_template.id) in resp_json['template']['uri']
            assert mocked.called


def test_post_sms_notification_returns_404_and_missing_template(notify_api, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'phone_number': '+447700900855',
                'template_id': str(uuid.uuid4())
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
            assert error_json['errors'] == [{"error": "BadRequestError",
                                             "message": 'Template not found'}]


def test_post_sms_notification_returns_403_and_well_formed_auth_error(notify_api, sample_template):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'phone_number': '+447700900855',
                'template_id': str(sample_template.id)
            }

            response = client.post(
                path='/v2/notifications/sms',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json')])

            assert response.status_code == 401
            assert response.headers['Content-type'] == 'application/json'
            error_resp = json.loads(response.get_data(as_text=True))
            assert error_resp['status_code'] == 401
            assert error_resp['errors'] == [{'error': "AuthError",
                                             'message': 'Unauthorized, authentication token must be provided'}]


def test_post_sms_notification_returns_400_and_for_schema_problems(notify_api, sample_template):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'phone_number': '+447700900855',
                'template': str(sample_template.id)
            }
            auth_header = create_authorization_header(service_id=sample_template.service_id)

            response = client.post(
                path='/v2/notifications/sms',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            assert response.status_code == 400
            assert response.headers['Content-type'] == 'application/json'
            error_resp = json.loads(response.get_data(as_text=True))
            assert error_resp['status_code'] == 400
            assert error_resp['errors'] == [{'error': 'ValidationError',
                                             'message': "template_id is a required property"
                                             }]


def test_post_email_notification_returns_201(client, sample_email_template, mocker):
    mocked = mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    data = {
        "reference": "reference from caller",
        "email_address": sample_email_template.service.users[0].email_address,
        "template_id": sample_email_template.id,
    }
    auth_header = create_authorization_header(service_id=sample_email_template.service_id)
    response = client.post(
        path="v2/notifications/email",
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header])
    assert response.status_code == 201
    resp_json = json.loads(response.get_data(as_text=True))
    notification = Notification.query.first()
    assert resp_json['id'] == str(notification.id)
    assert resp_json['reference'] == "reference from caller"
    assert notification.reference is None
    assert resp_json['content']['body'] == sample_email_template.content
    assert resp_json['content']['subject'] == sample_email_template.subject
    assert resp_json['content']['from_email'] == sample_email_template.service.email_from
    assert 'v2/notifications/{}'.format(notification.id) in resp_json['uri']
    assert resp_json['template']['id'] == str(sample_email_template.id)
    assert resp_json['template']['version'] == sample_email_template.version
    assert 'v2/templates/{}'.format(sample_email_template.id) in resp_json['template']['uri']
    assert mocked.called


def test_post_email_notification_returns_404_and_missing_template(notify_api, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                "email_address": sample_service.users[0].email_address,
                'template_id': str(uuid.uuid4())
            }
            auth_header = create_authorization_header(service_id=sample_service.id)

            response = client.post(
                path='/v2/notifications/email',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            assert response.status_code == 400
            assert response.headers['Content-type'] == 'application/json'

            error_json = json.loads(response.get_data(as_text=True))
            assert error_json['status_code'] == 400
            assert error_json['errors'] == [{"error": "BadRequestError",
                                             "message": 'Template not found'}]
