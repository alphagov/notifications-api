import uuid

from flask import json

from tests import create_authorization_header


def test_post_sms_notification_returns_201(notify_api, sample_template, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocked = mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')
            data = {
                'phone_number': '+447700900855',
                'template_id': str(sample_template.id)
            }
            auth_header = create_authorization_header(service_id=sample_template.service_id)

            response = client.post(
                path='/v2/notifications/sms',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            assert response.status_code == 201
            resp_json = json.loads(response.get_data(as_text=True))
            assert resp_json['id'] is not None
            assert resp_json['reference'] is None
            assert resp_json['template']['id'] == str(sample_template.id)
            assert resp_json['template']['version'] == sample_template.version
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
            assert error_json['code'] == 10400
            assert error_json['message'] == 'Template not found'
            assert error_json['fields'] == [{'template': 'Template not found'}]
            assert error_json['link'] == 'link to documentation'


def test_post_sms_notification_returns_403_and_well_formed_auth_error(notify_api, sample_template, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocked = mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')
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
            assert error_resp['code'] == 401
            assert error_resp['message'] == {'token': ['Unauthorized, authentication token must be provided']}
