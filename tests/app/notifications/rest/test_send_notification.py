from datetime import datetime
import random
import string

from unittest.mock import ANY
from flask import (json, current_app)
from freezegun import freeze_time
from notifications_python_client.authentication import create_jwt_token

import app
from app import encryption
from app.models import ApiKey, KEY_TYPE_TEAM
from app.dao.templates_dao import dao_get_all_templates_for_service, dao_update_template
from app.dao.services_dao import dao_update_service
from app.dao.api_key_dao import save_model_api_key
from tests import create_authorization_header
from tests.app.conftest import (
    sample_notification as create_sample_notification,
    sample_service as create_sample_service,
    sample_email_template as create_sample_email_template,
    sample_template as create_sample_template
)


def test_create_sms_should_reject_if_missing_required_fields(notify_api, sample_api_key, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.send_sms.apply_async')

            data = {}
            auth_header = create_authorization_header(service_id=sample_api_key.service_id)

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
            auth_header = create_authorization_header(service_id=sample_template.service_id)

            response = client.post(
                path='/notifications/sms',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            json_resp = json.loads(response.get_data(as_text=True))
            app.celery.tasks.send_sms.apply_async.assert_not_called()
            assert json_resp['result'] == 'error'
            assert len(json_resp['message'].keys()) == 1
            assert 'Invalid phone number: Must not contain letters or symbols' in json_resp['message']['to']
            assert response.status_code == 400


def test_send_notification_invalid_template_id(notify_api, sample_template, mocker, fake_uuid):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.send_sms.apply_async')

            data = {
                'to': '+447700900855',
                'template': fake_uuid
            }
            auth_header = create_authorization_header(service_id=sample_template.service_id)

            response = client.post(
                path='/notifications/sms',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            json_resp = json.loads(response.get_data(as_text=True))
            app.celery.tasks.send_sms.apply_async.assert_not_called()

            assert response.status_code == 404
            test_string = 'No result found'
            assert test_string in json_resp['message']


@freeze_time("2016-01-01 11:09:00.061258")
def test_send_notification_with_placeholders_replaced(notify_api, sample_email_template_with_placeholders, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.send_email.apply_async')

            data = {
                'to': 'ok@ok.com',
                'template': str(sample_email_template_with_placeholders.id),
                'personalisation': {
                    'name': 'Jo'
                }
            }
            auth_header = create_authorization_header(service_id=sample_email_template_with_placeholders.service.id)

            response = client.post(
                path='/notifications/email',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            response_data = json.loads(response.data)['data']
            notification_id = response_data['notification']['id']
            data.update({"template_version": sample_email_template_with_placeholders.version})

            app.celery.tasks.send_email.apply_async.assert_called_once_with(
                (str(sample_email_template_with_placeholders.service.id),
                 notification_id,
                 ANY,
                 "2016-01-01T11:09:00.061258"),
                kwargs=ANY,
                queue="email"
            )
            assert response.status_code == 201
            assert encryption.decrypt(app.celery.tasks.send_email.apply_async.call_args[0][0][2]) == data
            assert response_data['body'] == 'Hello Jo'
            assert response_data['subject'] == 'Jo'


def test_should_not_send_notification_for_archived_template(notify_api, sample_template):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            sample_template.archived = True
            dao_update_template(sample_template)
            json_data = json.dumps({
                'to': '+447700900855',
                'template': sample_template.id
            })
            auth_header = create_authorization_header(service_id=sample_template.service_id)

            resp = client.post(
                path='/notifications/sms',
                data=json_data,
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 400
            json_resp = json.loads(resp.get_data(as_text=True))
            assert 'Template has been deleted' in json_resp['message']['template']


def test_send_notification_with_missing_personalisation(notify_api, sample_template_with_placeholders, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.send_sms.apply_async')

            data = {
                'to': '+447700900855',
                'template': sample_template_with_placeholders.id,
                'personalisation': {
                    'foo': 'bar'
                }
            }
            auth_header = create_authorization_header(service_id=sample_template_with_placeholders.service.id)

            response = client.post(
                path='/notifications/sms',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            json_resp = json.loads(response.get_data(as_text=True))
            app.celery.tasks.send_sms.apply_async.assert_not_called()

            assert response.status_code == 400
            assert 'Missing personalisation: name' in json_resp['message']['template']


def test_send_notification_with_too_much_personalisation_data(
        notify_api, sample_template_with_placeholders, mocker
):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.send_sms.apply_async')

            data = {
                'to': '+447700900855',
                'template': sample_template_with_placeholders.id,
                'personalisation': {
                    'name': 'Jo', 'foo': 'bar'
                }
            }
            auth_header = create_authorization_header(service_id=sample_template_with_placeholders.service.id)

            response = client.post(
                path='/notifications/sms',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            json_resp = json.loads(response.get_data(as_text=True))
            app.celery.tasks.send_sms.apply_async.assert_not_called()

            assert response.status_code == 400
            assert 'Personalisation not needed for template: foo' in json_resp['message']['template']


def test_should_not_send_sms_if_restricted_and_not_a_service_user(notify_api, sample_template, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.send_sms.apply_async')

            sample_template.service.restricted = True
            dao_update_service(sample_template.service)
            invalid_mob = '+447700900855'
            data = {
                'to': invalid_mob,
                'template': sample_template.id
            }

            auth_header = create_authorization_header(service_id=sample_template.service_id)

            response = client.post(
                path='/notifications/sms',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            json_resp = json.loads(response.get_data(as_text=True))
            app.celery.tasks.send_sms.apply_async.assert_not_called()

            assert response.status_code == 400
            assert 'Invalid phone number for restricted service' in json_resp['message']['to']


def test_should_send_sms_if_restricted_and_a_service_user(notify_api, sample_template, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.send_sms.apply_async')

            sample_template.service.restricted = True
            dao_update_service(sample_template.service)
            data = {
                'to': sample_template.service.created_by.mobile_number,
                'template': sample_template.id
            }

            auth_header = create_authorization_header(service_id=sample_template.service_id)

            response = client.post(
                path='/notifications/sms',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            assert app.celery.tasks.send_sms.apply_async.called
            assert response.status_code == 201


def test_should_send_email_if_restricted_and_a_service_user(notify_api, sample_email_template, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.send_email.apply_async')

            sample_email_template.service.restricted = True
            dao_update_service(sample_email_template.service)
            data = {
                'to': sample_email_template.service.created_by.email_address,
                'template': sample_email_template.id
            }

            auth_header = create_authorization_header(service_id=sample_email_template.service_id)

            response = client.post(
                path='/notifications/email',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            assert app.celery.tasks.send_email.apply_async.called
            assert response.status_code == 201


def test_should_not_allow_template_from_another_service(notify_api, service_factory, sample_user, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.send_sms.apply_async')

            service_1 = service_factory.get('service 1', user=sample_user, email_from='service.1')
            service_2 = service_factory.get('service 2', user=sample_user, email_from='service.2')

            service_2_templates = dao_get_all_templates_for_service(service_id=service_2.id)
            data = {
                'to': sample_user.mobile_number,
                'template': service_2_templates[0].id
            }

            auth_header = create_authorization_header(service_id=service_1.id)

            response = client.post(
                path='/notifications/sms',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            json_resp = json.loads(response.get_data(as_text=True))
            app.celery.tasks.send_sms.apply_async.assert_not_called()

            assert response.status_code == 404
            test_string = 'No result found'
            assert test_string in json_resp['message']


def test_should_not_allow_template_content_too_large(notify_api, notify_db, notify_db_session, sample_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            template = create_sample_template(notify_db, notify_db_session, content="((long_text))")
            limit = current_app.config.get('SMS_CHAR_COUNT_LIMIT')
            json_data = json.dumps({
                'to': sample_user.mobile_number,
                'template': template.id,
                'personalisation': {
                    'long_text': ''.join(
                        random.choice(string.ascii_uppercase + string.digits) for _ in range(limit + 1))
                }
            })
            auth_header = create_authorization_header(service_id=template.service_id)

            resp = client.post(
                path='/notifications/sms',
                data=json_data,
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 400
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['message']['content'][0] == (
                'Content has a character count greater'
                ' than the limit of {}').format(limit)


@freeze_time("2016-01-01 11:09:00.061258")
def test_should_allow_valid_sms_notification(notify_api, sample_template, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.send_sms.apply_async')
            mocker.patch('app.encryption.encrypt', return_value="something_encrypted")

            data = {
                'to': '07700 900 855',
                'template': str(sample_template.id)
            }

            auth_header = create_authorization_header(service_id=sample_template.service_id)

            response = client.post(
                path='/notifications/sms',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            response_data = json.loads(response.data)['data']
            notification_id = response_data['notification']['id']
            assert app.encryption.encrypt.call_args[0][0]['to'] == '+447700900855'
            assert app.encryption.encrypt.call_args[0][0]['template'] == str(sample_template.id)
            assert app.encryption.encrypt.call_args[0][0]['template_version'] == sample_template.version

            app.celery.tasks.send_sms.apply_async.assert_called_once_with(
                (str(sample_template.service_id),
                 notification_id,
                 "something_encrypted",
                 "2016-01-01T11:09:00.061258"),
                kwargs=ANY,
                queue="sms"
            )
            assert response.status_code == 201
            assert notification_id
            assert 'subject' not in response_data
            assert response_data['body'] == sample_template.content
            assert response_data['template_version'] == sample_template.version


def test_create_email_should_reject_if_missing_required_fields(notify_api, sample_api_key, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.send_email.apply_async')

            data = {}
            auth_header = create_authorization_header(service_id=sample_api_key.service_id)

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
                'template': str(sample_email_template.service_id)
            }
            auth_header = create_authorization_header(service_id=sample_email_template.service_id)

            response = client.post(
                path='/notifications/email',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            data = json.loads(response.get_data(as_text=True))
            app.celery.tasks.send_email.apply_async.assert_not_called()
            assert response.status_code == 400
            assert data['result'] == 'error'
            assert data['message']['to'][0] == 'Not a valid email address'


def test_should_reject_email_notification_with_template_id_that_cant_be_found(
        notify_api, sample_email_template, mocker, fake_uuid):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.send_email.apply_async')
            data = {
                'to': 'ok@ok.com',
                'template': fake_uuid
            }
            auth_header = create_authorization_header(service_id=sample_email_template.service_id)

            response = client.post(
                path='/notifications/email',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            data = json.loads(response.get_data(as_text=True))
            app.celery.tasks.send_email.apply_async.assert_not_called()
            assert response.status_code == 404
            assert data['result'] == 'error'
            test_string = 'No result found'
            assert test_string in data['message']


def test_should_not_allow_email_template_from_another_service(notify_api, service_factory, sample_user, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.send_email.apply_async')

            service_1 = service_factory.get('service 1', template_type='email', user=sample_user,
                                            email_from='service.1')
            service_2 = service_factory.get('service 2', template_type='email', user=sample_user,
                                            email_from='service.2')

            service_2_templates = dao_get_all_templates_for_service(service_id=service_2.id)

            data = {
                'to': sample_user.email_address,
                'template': str(service_2_templates[0].id)
            }

            auth_header = create_authorization_header(service_id=service_1.id)

            response = client.post(
                path='/notifications/email',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            json_resp = json.loads(response.get_data(as_text=True))
            app.celery.tasks.send_email.apply_async.assert_not_called()

            assert response.status_code == 404
            test_string = 'No result found'
            assert test_string in json_resp['message']


def test_should_not_send_email_if_restricted_and_not_a_service_user(notify_api, sample_email_template, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.send_email.apply_async')

            sample_email_template.service.restricted = True
            dao_update_service(sample_email_template.service)

            data = {
                'to': "not-someone-we-trust@email-address.com",
                'template': str(sample_email_template.id)
            }

            auth_header = create_authorization_header(service_id=sample_email_template.service_id)

            response = client.post(
                path='/notifications/email',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            json_resp = json.loads(response.get_data(as_text=True))
            app.celery.tasks.send_email.apply_async.assert_not_called()

            assert response.status_code == 400
            assert 'Invalid email address for restricted service' in json_resp['message']['to']


@freeze_time("2016-01-01 11:09:00.061258")
def test_should_allow_valid_email_notification(notify_api, sample_email_template, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.send_email.apply_async')
            mocker.patch('app.encryption.encrypt', return_value="something_encrypted")

            data = {
                'to': 'ok@ok.com',
                'template': str(sample_email_template.id)
            }

            auth_header = create_authorization_header(service_id=sample_email_template.service_id)

            response = client.post(
                path='/notifications/email',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])
            assert response.status_code == 201
            response_data = json.loads(response.get_data(as_text=True))['data']
            notification_id = response_data['notification']['id']
            assert app.encryption.encrypt.call_args[0][0]['to'] == 'ok@ok.com'
            assert app.encryption.encrypt.call_args[0][0]['template'] == str(sample_email_template.id)
            assert app.encryption.encrypt.call_args[0][0]['template_version'] == sample_email_template.version
            app.celery.tasks.send_email.apply_async.assert_called_once_with(
                (str(sample_email_template.service_id),
                 notification_id,
                 "something_encrypted",
                 "2016-01-01T11:09:00.061258"),
                kwargs=ANY,
                queue="email"
            )

            assert response.status_code == 201
            assert notification_id
            assert response_data['subject'] == 'Email Subject'
            assert response_data['body'] == sample_email_template.content
            assert response_data['template_version'] == sample_email_template.version


@freeze_time("2016-01-01 12:00:00.061258")
def test_should_block_api_call_if_over_day_limit(notify_db, notify_db_session, notify_api, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.send_email.apply_async')
            mocker.patch('app.encryption.encrypt', return_value="something_encrypted")

            service = create_sample_service(notify_db, notify_db_session, limit=1, restricted=True)
            email_template = create_sample_email_template(notify_db, notify_db_session, service=service)
            create_sample_notification(
                notify_db, notify_db_session, template=email_template, service=service, created_at=datetime.utcnow()
            )

            data = {
                'to': 'ok@ok.com',
                'template': str(email_template.id)
            }

            auth_header = create_authorization_header(service_id=service.id)

            response = client.post(
                path='/notifications/email',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])
            json_resp = json.loads(response.get_data(as_text=True))

            assert response.status_code == 429
            assert 'Exceeded send limits (1) for today' in json_resp['message']


def test_no_limit_for_live_service(notify_api,
                                   notify_db,
                                   notify_db_session,
                                   mock_celery_send_email,
                                   sample_service,
                                   sample_email_template):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            sample_service.message_limit = 1
            notify_db.session.add(sample_service)
            notify_db.session.commit()

            data = {
                'to': 'ok@ok.com',
                'template': str(sample_email_template.id)
            }

            auth_header = create_authorization_header(service_id=sample_service.id)

            response = client.post(
                path='/notifications/email',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            assert response.status_code == 201


@freeze_time("2016-01-01 12:00:00.061258")
def test_should_block_api_call_if_over_day_limit_regardless_of_type(notify_db, notify_db_session, notify_api, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.send_sms.apply_async')
            mocker.patch('app.encryption.encrypt', return_value="something_encrypted")

            service = create_sample_service(notify_db, notify_db_session, limit=1, restricted=True)
            email_template = create_sample_email_template(notify_db, notify_db_session, service=service)
            sms_template = create_sample_template(notify_db, notify_db_session, service=service)
            create_sample_notification(
                notify_db, notify_db_session, template=email_template, service=service, created_at=datetime.utcnow()
            )

            data = {
                'to': '+447234123123',
                'template': str(sms_template.id)
            }

            auth_header = create_authorization_header(service_id=service.id)

            response = client.post(
                path='/notifications/sms',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])
            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 429
            assert 'Exceeded send limits (1) for today' in json_resp['message']


@freeze_time("2016-01-01 12:00:00.061258")
def test_should_allow_api_call_if_under_day_limit_regardless_of_type(notify_db, notify_db_session, notify_api, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.send_sms.apply_async')
            mocker.patch('app.encryption.encrypt', return_value="something_encrypted")

            service = create_sample_service(notify_db, notify_db_session, limit=2)
            email_template = create_sample_email_template(notify_db, notify_db_session, service=service)
            sms_template = create_sample_template(notify_db, notify_db_session, service=service)
            create_sample_notification(notify_db, notify_db_session, template=email_template, service=service)

            data = {
                'to': '+447634123123',
                'template': str(sms_template.id)
            }

            auth_header = create_authorization_header(service_id=service.id)

            response = client.post(
                path='/notifications/sms',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            assert response.status_code == 201


def test_should_record_email_request_in_statsd(notify_api, sample_email_template, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.statsd_client.incr')
            mocker.patch('app.celery.tasks.send_email.apply_async')
            mocker.patch('app.encryption.encrypt', return_value="something_encrypted")

            data = {
                'to': 'ok@ok.com',
                'template': str(sample_email_template.id)
            }

            auth_header = create_authorization_header(service_id=sample_email_template.service_id)

            response = client.post(
                path='/notifications/email',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])
            assert response.status_code == 201
            app.statsd_client.incr.assert_called_once_with("notifications.api.email")


def test_should_record_sms_request_in_statsd(notify_api, sample_template, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.statsd_client.incr')
            mocker.patch('app.celery.tasks.send_sms.apply_async')
            mocker.patch('app.encryption.encrypt', return_value="something_encrypted")

            data = {
                'to': '07123123123',
                'template': str(sample_template.id)
            }

            auth_header = create_authorization_header(service_id=sample_template.service_id)

            response = client.post(
                path='/notifications/sms',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])
            assert response.status_code == 201
            app.statsd_client.incr.assert_called_once_with("notifications.api.sms")


def test_should_not_return_html_in_body(notify_api, notify_db, notify_db_session, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.send_email.apply_async')
            email_template = create_sample_email_template(notify_db, notify_db.session, content='hello\nthere')

            data = {
                'to': 'ok@ok.com',
                'template': str(email_template.id)
            }

            auth_header = create_authorization_header(service_id=email_template.service_id)
            response = client.post(
                path='/notifications/email',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            assert response.status_code == 201
            assert json.loads(response.get_data(as_text=True))['data']['body'] == 'hello\nthere'


def test_should_not_send_email_if_team_api_key_and_not_a_service_user(notify_api, sample_email_template, mocker):
    with notify_api.test_request_context(), notify_api.test_client() as client:
        mocker.patch('app.celery.tasks.send_email.apply_async')

        data = {
            'to': "not-someone-we-trust@email-address.com",
            'template': str(sample_email_template.id),
        }

        # import pdb
        # pdb.set_trace()
        auth_header = create_authorization_header(service_id=sample_email_template.service_id, key_type=KEY_TYPE_TEAM)

        response = client.post(
            path='/notifications/email',
            data=json.dumps(data),
            headers=[('Content-Type', 'application/json'), auth_header])

        json_resp = json.loads(response.get_data(as_text=True))

        app.celery.tasks.send_email.apply_async.assert_not_called()

        assert response.status_code == 400
        assert 'Invalid email address for restricted service' in json_resp['message']['to']


def test_should_not_send_sms_if_team_api_key_and_not_a_service_user(notify_api, sample_template, mocker):
    with notify_api.test_request_context(), notify_api.test_client() as client:
        mocker.patch('app.celery.tasks.send_sms.apply_async')

        data = {
            'to': '07123123123',
            'template': str(sample_template.id),
        }

        auth_header = create_authorization_header(service_id=sample_template.service_id, key_type=KEY_TYPE_TEAM)

        response = client.post(
            path='/notifications/sms',
            data=json.dumps(data),
            headers=[('Content-Type', 'application/json'), auth_header])

        json_resp = json.loads(response.get_data(as_text=True))
        app.celery.tasks.send_sms.apply_async.assert_not_called()

        assert response.status_code == 400
        assert 'Invalid phone number for restricted service' in json_resp['message']['to']


def test_should_send_email_if_team_api_key_and_a_service_user(notify_api, sample_email_template, mocker):
    with notify_api.test_request_context(), notify_api.test_client() as client:
        mocker.patch('app.celery.tasks.send_email.apply_async')

        data = {
            'to': sample_email_template.service.created_by.email_address,
            'template': sample_email_template.id
        }
        api_key = ApiKey(service=sample_email_template.service,
                         name='team_key',
                         created_by=sample_email_template.created_by,
                         key_type=KEY_TYPE_TEAM)
        save_model_api_key(api_key)
        auth_header = create_jwt_token(secret=api_key.unsigned_secret, client_id=str(api_key.service_id))

        response = client.post(
            path='/notifications/email',
            data=json.dumps(data),
            headers=[('Content-Type', 'application/json'), ('Authorization', 'Bearer {}'.format(auth_header))])

        app.celery.tasks.send_email.apply_async.assert_called_once_with(
            ANY,
            kwargs={
                'api_key_id': str(api_key.id),
                'key_type': api_key.key_type
            },
            queue='email')
        assert response.status_code == 201


def test_should_send_sms_if_team_api_key_and_a_service_user(notify_api, sample_template, mocker):
    with notify_api.test_request_context(), notify_api.test_client() as client:
        mocker.patch('app.celery.tasks.send_sms.apply_async')

        data = {
            'to': sample_template.service.created_by.mobile_number,
            'template': sample_template.id
        }
        api_key = ApiKey(service=sample_template.service,
                         name='team_key',
                         created_by=sample_template.created_by,
                         key_type=KEY_TYPE_TEAM)
        save_model_api_key(api_key)
        auth_header = create_jwt_token(secret=api_key.unsigned_secret, client_id=str(api_key.service_id))

        response = client.post(
            path='/notifications/sms',
            data=json.dumps(data),
            headers=[('Content-Type', 'application/json'), ('Authorization', 'Bearer {}'.format(auth_header))])

        app.celery.tasks.send_sms.apply_async.assert_called_once_with(
            ANY,
            kwargs={
                'api_key_id': str(api_key.id),
                'key_type': api_key.key_type
            },
            queue='sms')
        assert response.status_code == 201
