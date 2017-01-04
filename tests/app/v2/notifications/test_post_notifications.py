import uuid

import pytest
from flask import json
from app.models import Notification
from tests import create_authorization_header


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
            # conftest fixture service does not have a sms sender, use config default
            assert resp_json['content']['from_number'] == notify_api.config["FROM_NUMBER"]
            assert 'v2/notifications/{}'.format(notification_id) in resp_json['uri']
            assert resp_json['template']['id'] == str(sample_template_with_placeholders.id)
            assert resp_json['template']['version'] == sample_template_with_placeholders.version
            assert 'services/{}/templates/{}'.format(sample_template_with_placeholders.service_id,
                                                     sample_template_with_placeholders.id) \
                   in resp_json['template']['uri']
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
    assert resp_json['content']['body'] == sample_email_template_with_placeholders.content\
        .replace('((name))', 'Bob').replace('GOV.UK', u'GOV.\u200bUK')
    assert resp_json['content']['subject'] == sample_email_template_with_placeholders.subject\
        .replace('((name))', 'Bob')
    assert resp_json['content']['from_email'] == sample_email_template_with_placeholders.service.email_from
    assert 'v2/notifications/{}'.format(notification.id) in resp_json['uri']
    assert resp_json['template']['id'] == str(sample_email_template_with_placeholders.id)
    assert resp_json['template']['version'] == sample_email_template_with_placeholders.version
    assert 'services/{}/templates/{}'.format(str(sample_email_template_with_placeholders.service_id),
                                             str(sample_email_template_with_placeholders.id)) \
           in resp_json['template']['uri']
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
