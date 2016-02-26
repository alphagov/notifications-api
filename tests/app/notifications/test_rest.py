import uuid
import app.celery.tasks
from tests import create_authorization_header
from flask import json
from app.models import Service
from app.dao.templates_dao import dao_get_all_templates_for_service
from app.dao.services_dao import dao_update_service
from freezegun import freeze_time


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

            assert response.status_code == 404
            assert len(json_resp['message'].keys()) == 1
            test_string = 'Template {} not found for service {}'.format(9999, sample_template.service.id)
            assert test_string in json_resp['message']['template']


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
            assert 'Invalid phone number for restricted service' in json_resp['message']['to']


def test_should_not_allow_template_from_another_service(notify_api, service_factory, sample_user, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.send_sms.apply_async')

            service_1 = service_factory.get('service 1', user=sample_user)
            service_2 = service_factory.get('service 2', user=sample_user)

            service_2_templates = dao_get_all_templates_for_service(service_id=service_2.id)
            data = {
                'to': sample_user.mobile_number,
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

            assert response.status_code == 404
            test_string = 'Template {} not found for service {}'.format(service_2_templates[0].id, service_1.id)
            assert test_string in json_resp['message']['template']


@freeze_time("2016-01-01 11:09:00.061258")
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
                 "something_encrypted",
                 "2016-01-01 11:09:00.061258"),
                queue="sms"
            )
            assert response.status_code == 201
            assert notification_id


def test_create_email_should_reject_if_missing_required_fields(notify_api, sample_api_key, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.send_email.apply_async')

            data = {}
            auth_header = create_authorization_header(
                service_id=sample_api_key.service_id,
                request_body=json.dumps(data),
                path='/notifications/email',
                method='POST')

            response = client.post(
                path='/notifications/email',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            json_resp = json.loads(response.get_data(as_text=True))
            app.celery.tasks.send_email.apply_async.assert_not_called()
            assert json_resp['result'] == 'error'
            assert 'Missing data for required field.' in json_resp['message']['to'][0]
            assert 'Missing data for required field.' in json_resp['message']['template'][0]
            assert response.status_code == 400


def test_should_reject_email_notification_with_bad_email(notify_api, sample_email_template, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.send_email.apply_async')
            to_address = "bad-email"
            data = {
                'to': to_address,
                'template': sample_email_template.service.id
            }
            auth_header = create_authorization_header(
                service_id=sample_email_template.service.id,
                request_body=json.dumps(data),
                path='/notifications/email',
                method='POST')

            response = client.post(
                path='/notifications/email',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            data = json.loads(response.get_data(as_text=True))
            app.celery.tasks.send_email.apply_async.assert_not_called()
            assert response.status_code == 400
            assert data['result'] == 'error'
            assert data['message']['to'][0] == 'Invalid email'


def test_should_reject_email_notification_with_template_id_that_cant_be_found(
        notify_api, sample_email_template, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.send_email.apply_async')
            data = {
                'to': 'ok@ok.com',
                'template': 1234
            }
            auth_header = create_authorization_header(
                service_id=sample_email_template.service.id,
                request_body=json.dumps(data),
                path='/notifications/email',
                method='POST')

            response = client.post(
                path='/notifications/email',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            data = json.loads(response.get_data(as_text=True))
            app.celery.tasks.send_email.apply_async.assert_not_called()
            assert response.status_code == 404
            assert data['result'] == 'error'
            test_string = 'Template {} not found for service {}'.format(
                1234,
                sample_email_template.service.id
            )
            assert test_string in data['message']['template']


def test_should_not_allow_email_template_from_another_service(notify_api, service_factory, sample_user, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.send_email.apply_async')

            service_1 = service_factory.get('service 1', template_type='email', user=sample_user)
            service_2 = service_factory.get('service 2', template_type='email', user=sample_user)

            service_2_templates = dao_get_all_templates_for_service(service_id=service_2.id)

            data = {
                'to': sample_user.email_address,
                'template': service_2_templates[0].id
            }

            auth_header = create_authorization_header(
                service_id=service_1.id,
                request_body=json.dumps(data),
                path='/notifications/email',
                method='POST')

            response = client.post(
                path='/notifications/email',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            json_resp = json.loads(response.get_data(as_text=True))
            app.celery.tasks.send_email.apply_async.assert_not_called()

            assert response.status_code == 404
            test_string = 'Template {} not found for service {}'.format(service_2_templates[0].id, service_1.id)
            assert test_string in json_resp['message']['template']


def test_should_not_send_email_if_restricted_and_not_a_service_user(notify_api, sample_email_template, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.send_email.apply_async')

            sample_email_template.service.restricted = True
            dao_update_service(sample_email_template)

            data = {
                'to': "not-someone-we-trust@email-address.com",
                'template': sample_email_template.id
            }

            auth_header = create_authorization_header(
                service_id=sample_email_template.service.id,
                request_body=json.dumps(data),
                path='/notifications/email',
                method='POST')

            response = client.post(
                path='/notifications/email',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            json_resp = json.loads(response.get_data(as_text=True))
            app.celery.tasks.send_email.apply_async.assert_not_called()

            assert response.status_code == 400
            assert 'Email address not permitted for restricted service' in json_resp['message']['to']


def test_should_not_send_email_for_job_if_restricted_and_not_a_service_user(
        notify_api,
        sample_job,
        sample_email_template,
        mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.send_email.apply_async')

            sample_email_template.service.restricted = True
            dao_update_service(sample_email_template)

            data = {
                'to': "not-someone-we-trust@email-address.com",
                'template': sample_job.template.id,
                'job': sample_job.id
            }

            auth_header = create_authorization_header(
                service_id=sample_job.service.id,
                request_body=json.dumps(data),
                path='/notifications/email',
                method='POST')

            response = client.post(
                path='/notifications/email',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            json_resp = json.loads(response.get_data(as_text=True))
            app.celery.tasks.send_email.apply_async.assert_not_called()

            assert response.status_code == 400
            assert 'Email address not permitted for restricted service' in json_resp['message']['to']


@freeze_time("2016-01-01 11:09:00.061258")
def test_should_allow_valid_email_notification(notify_api, sample_email_template, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.send_email.apply_async')
            mocker.patch('app.encryption.encrypt', return_value="something_encrypted")

            data = {
                'to': 'ok@ok.com',
                'template': sample_email_template.id
            }

            auth_header = create_authorization_header(
                request_body=json.dumps(data),
                path='/notifications/email',
                method='POST',
                service_id=sample_email_template.service_id
            )

            response = client.post(
                path='/notifications/email',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])
            assert response.status_code == 201
            notification_id = json.loads(response.get_data(as_text=True))['notification_id']
            app.celery.tasks.send_email.apply_async.assert_called_once_with(
                (str(sample_email_template.service_id),
                 notification_id,
                 "Email Subject",
                 "sample.service@test.notify.com",
                 "something_encrypted",
                 "2016-01-01 11:09:00.061258"),
                queue="email"
            )
            assert response.status_code == 201
            assert notification_id
