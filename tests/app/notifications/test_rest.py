import uuid
import app.celery.tasks

from tests import create_authorization_header
from flask import json
from app.models import Service
from app.dao.templates_dao import get_model_templates


def test_get_notification_by_id(notify_api, sample_notification):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header(
                service_id=sample_notification.service_id,
                path='/notifications/{}'.format(sample_notification.id),
                method='GET')

            response = client.get(
                '/notifications/{}'.format(sample_notification.id),
                headers=[auth_header])

            notification = json.loads(response.get_data(as_text=True))['notification']
            assert notification['status'] == 'sent'
            assert notification['template'] == sample_notification.template.id
            assert notification['to'] == '+44709123456'
            assert notification['service'] == str(sample_notification.service_id)
            assert response.status_code == 200


def test_get_notifications_empty_result(notify_api, sample_api_key):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:

            missing_notification_id = uuid.uuid4()
            auth_header = create_authorization_header(
                service_id=sample_api_key.service_id,
                path='/notifications/{}'.format(missing_notification_id),
                method='GET')

            response = client.get(
                path='/notifications/{}'.format(missing_notification_id),
                headers=[auth_header])

            notification = json.loads(response.get_data(as_text=True))
            assert notification['result'] == "error"
            assert notification['message'] == "not found"
            assert response.status_code == 404


def test_create_sms_should_reject_if_missing_required_fields(notify_api, sample_api_key, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.send_sms.apply_async')

            data = {}
            auth_header = create_authorization_header(
                service_id=sample_api_key.service_id,
                request_body=json.dumps(data),
                path='/notifications/sms',
                method='POST')

            response = client.post(
                path='/notifications/sms',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            json_resp = json.loads(response.get_data(as_text=True))
            app.celery.tasks.send_sms.apply_async.assert_not_called()
            assert json_resp['result'] == 'error'
            assert 'Missing data for required field.' in json_resp['message']['to'][0]
            assert 'Missing data for required field.' in json_resp['message']['template'][0]
            assert response.status_code == 400


def test_should_reject_bad_phone_numbers(notify_api, sample_template, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.send_sms.apply_async')

            data = {
                'to': 'invalid',
                'template': sample_template.id
            }
            auth_header = create_authorization_header(
                request_body=json.dumps(data),
                path='/notifications/sms',
                method='POST')

            response = client.post(
                path='/notifications/sms',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            json_resp = json.loads(response.get_data(as_text=True))
            app.celery.tasks.send_sms.apply_async.assert_not_called()

            assert json_resp['result'] == 'error'
            assert len(json_resp['message'].keys()) == 1
            assert 'Invalid phone number, must be of format +441234123123' in json_resp['message']['to']
            assert response.status_code == 400


def test_send_notification_invalid_template_id(notify_api, sample_template, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.send_sms.apply_async')

            data = {
                'to': '+441234123123',
                'template': 9999
            }
            auth_header = create_authorization_header(
                service_id=sample_template.service.id,
                request_body=json.dumps(data),
                path='/notifications/sms',
                method='POST')

            response = client.post(
                path='/notifications/sms',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            json_resp = json.loads(response.get_data(as_text=True))
            app.celery.tasks.send_sms.apply_async.assert_not_called()

            assert response.status_code == 400
            assert len(json_resp['message'].keys()) == 1
            assert 'Template not found' in json_resp['message']['template']


def test_prevents_sending_to_any_mobile_on_restricted_service(notify_api, sample_template, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.send_sms.apply_async')

            Service.query.filter_by(
                id=sample_template.service.id
            ).update(
                {'restricted': True}
            )
            invalid_mob = '+449999999999'
            data = {
                'to': invalid_mob,
                'template': sample_template.id
            }

            auth_header = create_authorization_header(
                service_id=sample_template.service.id,
                request_body=json.dumps(data),
                path='/notifications/sms',
                method='POST')

            response = client.post(
                path='/notifications/sms',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            json_resp = json.loads(response.get_data(as_text=True))
            app.celery.tasks.send_sms.apply_async.assert_not_called()

            assert response.status_code == 400
            assert 'Invalid phone number for restricted service' in json_resp['message']['restricted']


def test_should_not_allow_template_from_another_service(notify_api, service_factory, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.send_sms.apply_async')

            service_1 = service_factory.get('service 1')
            service_2 = service_factory.get('service 2')

            service_2_templates = get_model_templates(service_id=service_2.id)

            data = {
                'to': '+441234123123',
                'template': service_2_templates[0].id
            }

            auth_header = create_authorization_header(
                service_id=service_1.id,
                request_body=json.dumps(data),
                path='/notifications/sms',
                method='POST')

            response = client.post(
                path='/notifications/sms',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            json_resp = json.loads(response.get_data(as_text=True))
            app.celery.tasks.send_sms.apply_async.assert_not_called()

            assert response.status_code == 400
            assert 'Invalid template' in json_resp['message']['restricted']


def test_should_allow_valid_sms_notification(notify_api, sample_template, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.send_sms.apply_async')
            mocker.patch('app.encryption.encrypt', return_value="something_encrypted")

            data = {
                'to': '+441234123123',
                'template': sample_template.id
            }

            auth_header = create_authorization_header(
                request_body=json.dumps(data),
                path='/notifications/sms',
                method='POST',
                service_id=sample_template.service_id
            )

            response = client.post(
                path='/notifications/sms',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            notification_id = json.loads(response.data)['notification_id']
            app.celery.tasks.send_sms.apply_async.assert_called_once_with(
                (str(sample_template.service_id),
                 notification_id,
                 "something_encrypted")
            )
            assert response.status_code == 201
            assert notification_id


def test_send_email_valid_data(notify_api,
                               notify_db,
                               notify_db_session,
                               sample_service,
                               sample_admin_service_id,
                               sqs_client_conn,
                               mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            to_address = "to@notify.com"
            from_address = "from@notify.com"
            subject = "This is the subject"
            message = "This is the message"
            data = {
                'to': to_address,
                'from': from_address,
                'subject': subject,
                'message': message
            }
            auth_header = create_authorization_header(
                request_body=json.dumps(data),
                path='/notifications/email',
                method='POST')

            response = client.post(
                path='/notifications/email',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            assert response.status_code == 201
            assert json.loads(response.data)['notification_id'] is not None


def test_valid_message_with_service_id(notify_api,
                                       notify_db,
                                       notify_db_session,
                                       sqs_client_conn,
                                       sample_user,
                                       sample_template,
                                       mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            job_id = uuid.uuid4()
            service_id = sample_template.service.id
            url = '/notifications/sms/service/{}'.format(service_id)
            data = {
                'to': '+441234123123',
                'template': sample_template.id,
                'job': job_id
            }
            auth_header = create_authorization_header(
                request_body=json.dumps(data),
                path=url,
                method='POST')

            response = client.post(
                url,
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            assert response.status_code == 201
            assert json.loads(response.data)['notification_id'] is not None


def test_message_with_incorrect_service_id_should_fail(notify_api,
                                                       notify_db,
                                                       notify_db_session,
                                                       sqs_client_conn,
                                                       sample_user,
                                                       sample_template,
                                                       mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            job_id = uuid.uuid4()
            invalid_service_id = uuid.uuid4()

            url = '/notifications/sms/service/{}'.format(invalid_service_id)

            data = {
                'to': '+441234123123',
                'template': sample_template.id,
                'job': job_id
            }

            auth_header = create_authorization_header(
                request_body=json.dumps(data),
                path=url,
                method='POST')

            response = client.post(
                url,
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 400
            expected_error = 'Invalid template: id {} for service id: {}'.format(sample_template.id,
                                                                                 invalid_service_id)
            assert json_resp['message'] == expected_error
