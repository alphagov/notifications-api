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


def test_post_sms_notification_returns_404_when_template_is_wrong_type(notify_api, sample_email_template):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'phone_number': '+447700900855',
                'template_id': str(sample_email_template.id)
            }
            auth_header = create_authorization_header(service_id=sample_email_template.service_id)

            response = client.post(
                path='/v2/notifications/sms',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            assert response.status_code == 400
            resp_text = json.loads(response.get_data(as_text=True))
            assert resp_text['code'] == '10400'
            assert resp_text['message'] == '{0} template is not suitable for {1} notification'.format('email', 'sms')
            assert resp_text['link'] == 'link to documentation'
            assert resp_text.get('fields', None) is None
