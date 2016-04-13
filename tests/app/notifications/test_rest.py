from datetime import datetime
import uuid
import app.celery.tasks
from tests import create_authorization_header
from tests.app.conftest import sample_notification as create_sample_notification
from tests.app.conftest import sample_job as create_sample_job
from tests.app.conftest import sample_service as create_sample_service
from tests.app.conftest import sample_email_template as create_sample_email_template
from tests.app.conftest import sample_template as create_sample_template
from flask import json
from app.models import Service
from app.dao.templates_dao import dao_get_all_templates_for_service
from app.dao.services_dao import dao_update_service
from app.dao.notifications_dao import get_notification_by_id, dao_get_notification_statistics_for_service
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

            notification = json.loads(response.get_data(as_text=True))['data']['notification']
            assert notification['status'] == 'sending'
            assert notification['template'] == {
                'id': str(sample_notification.template.id),
                'name': sample_notification.template.name,
                'template_type': sample_notification.template.template_type}
            assert notification['job'] == {
                'id': str(sample_notification.job.id),
                'original_file_name': sample_notification.job.original_file_name
            }
            assert notification['to'] == '+447700900855'
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
            assert notification['message'] == "No result found"
            assert response.status_code == 404


def test_get_all_notifications(notify_api, sample_notification):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header(
                service_id=sample_notification.service_id,
                path='/notifications',
                method='GET')

            response = client.get(
                '/notifications',
                headers=[auth_header])

            notifications = json.loads(response.get_data(as_text=True))
            assert notifications['notifications'][0]['status'] == 'sending'
            assert notifications['notifications'][0]['template'] == {
                'id': str(sample_notification.template.id),
                'name': sample_notification.template.name,
                'template_type': sample_notification.template.template_type}
            assert notifications['notifications'][0]['job'] == {
                'id': str(sample_notification.job.id),
                'original_file_name': sample_notification.job.original_file_name
            }
            assert notifications['notifications'][0]['to'] == '+447700900855'
            assert notifications['notifications'][0]['service'] == str(sample_notification.service_id)
            assert response.status_code == 200


def test_get_all_notifications_newest_first(notify_api, notify_db, notify_db_session, sample_email_template):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            notification_1 = create_sample_notification(notify_db, notify_db_session, sample_email_template.service)
            notification_2 = create_sample_notification(notify_db, notify_db_session, sample_email_template.service)
            notification_3 = create_sample_notification(notify_db, notify_db_session, sample_email_template.service)

            auth_header = create_authorization_header(
                service_id=sample_email_template.service_id,
                path='/notifications',
                method='GET')

            response = client.get(
                '/notifications',
                headers=[auth_header])

            notifications = json.loads(response.get_data(as_text=True))
            assert len(notifications['notifications']) == 3
            assert notifications['notifications'][0]['to'] == notification_3.to
            assert notifications['notifications'][1]['to'] == notification_2.to
            assert notifications['notifications'][2]['to'] == notification_1.to
            assert response.status_code == 200


def test_get_all_notifications_for_service_in_order(notify_api, notify_db, notify_db_session):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            service_1 = create_sample_service(notify_db, notify_db_session, service_name="1", email_from='1')
            service_2 = create_sample_service(notify_db, notify_db_session, service_name="2", email_from='2')

            create_sample_notification(notify_db, notify_db_session, service=service_2)

            notification_1 = create_sample_notification(notify_db, notify_db_session, service=service_1)
            notification_2 = create_sample_notification(notify_db, notify_db_session, service=service_1)
            notification_3 = create_sample_notification(notify_db, notify_db_session, service=service_1)

            auth_header = create_authorization_header(
                path='/service/{}/notifications'.format(service_1.id),
                method='GET')

            response = client.get(
                path='/service/{}/notifications'.format(service_1.id),
                headers=[auth_header])

            resp = json.loads(response.get_data(as_text=True))
            assert len(resp['notifications']) == 3
            assert resp['notifications'][0]['to'] == notification_3.to
            assert resp['notifications'][1]['to'] == notification_2.to
            assert resp['notifications'][2]['to'] == notification_1.to
            assert response.status_code == 200


def test_get_all_notifications_for_job_in_order(notify_api, notify_db, notify_db_session, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            main_job = create_sample_job(notify_db, notify_db_session, service=sample_service)
            another_job = create_sample_job(notify_db, notify_db_session, service=sample_service)

            notification_1 = create_sample_notification(
                notify_db, notify_db_session, job=main_job, to_field="1", created_at=datetime.utcnow()
            )
            notification_2 = create_sample_notification(
                notify_db, notify_db_session, job=main_job, to_field="2", created_at=datetime.utcnow()
            )
            notification_3 = create_sample_notification(
                notify_db, notify_db_session, job=main_job, to_field="3", created_at=datetime.utcnow()
            )
            create_sample_notification(notify_db, notify_db_session, job=another_job)

            auth_header = create_authorization_header(
                path='/service/{}/job/{}/notifications'.format(sample_service.id, main_job.id),
                method='GET')

            response = client.get(
                path='/service/{}/job/{}/notifications'.format(sample_service.id, main_job.id),
                headers=[auth_header])

            resp = json.loads(response.get_data(as_text=True))
            assert len(resp['notifications']) == 3
            assert resp['notifications'][0]['to'] == notification_3.to
            assert resp['notifications'][1]['to'] == notification_2.to
            assert resp['notifications'][2]['to'] == notification_1.to
            assert response.status_code == 200


def test_should_not_get_notifications_by_service_with_client_credentials(notify_api, sample_api_key):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header(
                service_id=sample_api_key.service.id,
                path='/service/{}/notifications'.format(sample_api_key.service.id),
                method='GET')

            response = client.get(
                '/service/{}/notifications'.format(sample_api_key.service.id),
                headers=[auth_header])

            resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 403
            assert resp['result'] == 'error'
            assert resp['message'] == 'Forbidden, invalid authentication token provided'


def test_should_not_get_notifications_by_job_and_service_with_client_credentials(notify_api, sample_job):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header(
                service_id=sample_job.service.id,
                path='/service/{}/job/{}/notifications'.format(sample_job.service.id, sample_job.id),
                method='GET')

            response = client.get(
                '/service/{}/job/{}/notifications'.format(sample_job.service.id, sample_job.id),
                headers=[auth_header])

            resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 403
            assert resp['result'] == 'error'
            assert resp['message'] == 'Forbidden, invalid authentication token provided'


def test_should_reject_invalid_page_param(notify_api, sample_email_template):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header(
                service_id=sample_email_template.service_id,
                path='/notifications',
                method='GET')

            response = client.get(
                '/notifications?page=invalid',
                headers=[auth_header])

            notifications = json.loads(response.get_data(as_text=True))
            assert response.status_code == 400
            assert notifications['result'] == 'error'
            assert 'Not a valid integer.' in notifications['message']['page']


def test_should_return_pagination_links(notify_api, notify_db, notify_db_session, sample_email_template):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            # Effectively mocking page size
            original_page_size = notify_api.config['PAGE_SIZE']
            try:
                notify_api.config['PAGE_SIZE'] = 1

                create_sample_notification(notify_db, notify_db_session, sample_email_template.service)
                notification_2 = create_sample_notification(notify_db, notify_db_session, sample_email_template.service)
                create_sample_notification(notify_db, notify_db_session, sample_email_template.service)

                auth_header = create_authorization_header(
                    service_id=sample_email_template.service_id,
                    path='/notifications',
                    method='GET')

                response = client.get(
                    '/notifications?page=2',
                    headers=[auth_header])

                notifications = json.loads(response.get_data(as_text=True))
                assert len(notifications['notifications']) == 1
                assert notifications['links']['last'] == '/notifications?page=3'
                assert notifications['links']['prev'] == '/notifications?page=1'
                assert notifications['links']['next'] == '/notifications?page=3'
                assert notifications['notifications'][0]['to'] == notification_2.to
                assert response.status_code == 200

            finally:
                notify_api.config['PAGE_SIZE'] = original_page_size


def test_get_all_notifications_returns_empty_list(notify_api, sample_api_key):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header(
                service_id=sample_api_key.service.id,
                path='/notifications',
                method='GET')

            response = client.get(
                '/notifications',
                headers=[auth_header])

            notifications = json.loads(response.get_data(as_text=True))
            assert response.status_code == 200
            assert len(notifications['notifications']) == 0


def test_filter_by_template_type(notify_api, notify_db, notify_db_session, sample_template, sample_email_template):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:

            notification_1 = create_sample_notification(
                notify_db,
                notify_db_session,
                service=sample_email_template.service,
                template=sample_template)
            notification_2 = create_sample_notification(
                notify_db,
                notify_db_session,
                service=sample_email_template.service,
                template=sample_email_template)

            auth_header = create_authorization_header(
                service_id=sample_email_template.service_id,
                path='/notifications',
                method='GET')

            response = client.get(
                '/notifications?template_type=sms',
                headers=[auth_header])

            notifications = json.loads(response.get_data(as_text=True))
            assert len(notifications['notifications']) == 1
            assert notifications['notifications'][0]['template']['template_type'] == 'sms'
            assert response.status_code == 200


def test_filter_by_multiple_template_types(notify_api,
                                           notify_db,
                                           notify_db_session,
                                           sample_template,
                                           sample_email_template):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:

            notification_1 = create_sample_notification(
                notify_db,
                notify_db_session,
                service=sample_email_template.service,
                template=sample_template)
            notification_2 = create_sample_notification(
                notify_db,
                notify_db_session,
                service=sample_email_template.service,
                template=sample_email_template)

            auth_header = create_authorization_header(
                service_id=sample_email_template.service_id,
                path='/notifications',
                method='GET')

            response = client.get(
                '/notifications?template_type=sms&template_type=email',
                headers=[auth_header])

            assert response.status_code == 200
            notifications = json.loads(response.get_data(as_text=True))
            assert len(notifications['notifications']) == 2
            set(['sms', 'email']) == set(
                [x['template']['template_type'] for x in notifications['notifications']])


def test_filter_by_status(notify_api, notify_db, notify_db_session, sample_email_template):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:

            notification_1 = create_sample_notification(
                notify_db,
                notify_db_session,
                service=sample_email_template.service,
                template=sample_email_template,
                status="delivered")

            notification_2 = create_sample_notification(
                notify_db,
                notify_db_session,
                service=sample_email_template.service,
                template=sample_email_template)

            auth_header = create_authorization_header(
                service_id=sample_email_template.service_id,
                path='/notifications',
                method='GET')

            response = client.get(
                '/notifications?status=delivered',
                headers=[auth_header])

            notifications = json.loads(response.get_data(as_text=True))
            assert len(notifications['notifications']) == 1
            assert notifications['notifications'][0]['status'] == 'delivered'
            assert response.status_code == 200


def test_filter_by_multiple_statuss(notify_api,
                                    notify_db,
                                    notify_db_session,
                                    sample_email_template):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:

            notification_1 = create_sample_notification(
                notify_db,
                notify_db_session,
                service=sample_email_template.service,
                template=sample_email_template,
                status="delivered")

            notification_2 = create_sample_notification(
                notify_db,
                notify_db_session,
                service=sample_email_template.service,
                template=sample_email_template)

            auth_header = create_authorization_header(
                service_id=sample_email_template.service_id,
                path='/notifications',
                method='GET')

            response = client.get(
                '/notifications?status=delivered&status=sending',
                headers=[auth_header])

            assert response.status_code == 200
            notifications = json.loads(response.get_data(as_text=True))
            assert len(notifications['notifications']) == 2
            set(['delivered', 'sending']) == set(
                [x['status'] for x in notifications['notifications']])


def test_filter_by_status_and_template_type(notify_api,
                                            notify_db,
                                            notify_db_session,
                                            sample_template,
                                            sample_email_template):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:

            notification_1 = create_sample_notification(
                notify_db,
                notify_db_session,
                service=sample_email_template.service,
                template=sample_template)
            notification_2 = create_sample_notification(
                notify_db,
                notify_db_session,
                service=sample_email_template.service,
                template=sample_email_template)
            notification_3 = create_sample_notification(
                notify_db,
                notify_db_session,
                service=sample_email_template.service,
                template=sample_email_template,
                status="delivered")

            auth_header = create_authorization_header(
                service_id=sample_email_template.service_id,
                path='/notifications',
                method='GET')

            response = client.get(
                '/notifications?template_type=email&status=delivered',
                headers=[auth_header])

            notifications = json.loads(response.get_data(as_text=True))
            assert len(notifications['notifications']) == 1
            assert notifications['notifications'][0]['template']['template_type'] == 'email'
            assert notifications['notifications'][0]['status'] == 'delivered'
            assert response.status_code == 200


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
            test_string = 'No result found'
            assert test_string in json_resp['message']


@freeze_time("2016-01-01 11:09:00.061258")
def test_send_notification_with_placeholders_replaced(notify_api, sample_template_with_placeholders, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.send_sms.apply_async')
            mocker.patch('app.encryption.encrypt', return_value="something_encrypted")

            data = {
                'to': '+447700900855',
                'template': sample_template_with_placeholders.id,
                'personalisation': {
                    'name': 'Jo'
                }
            }
            auth_header = create_authorization_header(
                service_id=sample_template_with_placeholders.service.id,
                request_body=json.dumps(data),
                path='/notifications/sms',
                method='POST')

            response = client.post(
                path='/notifications/sms',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            notification_id = json.loads(response.data)['data']['notification']['id']

            app.celery.tasks.send_sms.apply_async.assert_called_once_with(
                (str(sample_template_with_placeholders.service.id),
                 notification_id,
                 "something_encrypted",
                 "2016-01-01T11:09:00.061258"),
                queue="sms"
            )
            assert response.status_code == 201


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
            auth_header = create_authorization_header(
                service_id=sample_template_with_placeholders.service.id,
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
            auth_header = create_authorization_header(
                service_id=sample_template_with_placeholders.service.id,
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
            assert 'Personalisation not needed for template: foo' in json_resp['message']['template']


def test_prevents_sending_to_any_mobile_on_restricted_service(notify_api, sample_template, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.send_sms.apply_async')

            Service.query.filter_by(
                id=sample_template.service.id
            ).update(
                {'restricted': True}
            )
            invalid_mob = '+447700900855'
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

            service_1 = service_factory.get('service 1', user=sample_user, email_from='service.1')
            service_2 = service_factory.get('service 2', user=sample_user, email_from='service.2')

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
            test_string = 'No result found'
            assert test_string in json_resp['message']


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

            notification_id = json.loads(response.data)['data']['notification']['id']
            assert app.encryption.encrypt.call_args[0][0]['to'] == '+447700900855'
            app.celery.tasks.send_sms.apply_async.assert_called_once_with(
                (str(sample_template.service_id),
                 notification_id,
                 "something_encrypted",
                 "2016-01-01T11:09:00.061258"),
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
                'template': str(sample_email_template.service.id)
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
            test_string = 'No result found'
            assert test_string in json_resp['message']


def test_should_not_send_email_if_restricted_and_not_a_service_user(notify_api, sample_email_template, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.send_email.apply_async')

            sample_email_template.service.restricted = True
            dao_update_service(sample_email_template)

            data = {
                'to': "not-someone-we-trust@email-address.com",
                'template': str(sample_email_template.id)
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
            assert 'Invalid email address for restricted service' in json_resp['message']['to']


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
                'template': str(sample_job.template.id),
                'job': (sample_job.id)
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
            notification_id = json.loads(response.get_data(as_text=True))['data']['notification']['id']
            app.celery.tasks.send_email.apply_async.assert_called_once_with(
                (str(sample_email_template.service_id),
                 notification_id,
                 "sample.service@test.notify.com",
                 "something_encrypted",
                 "2016-01-01T11:09:00.061258"),
                queue="email"
            )
            assert response.status_code == 201
            assert notification_id


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

            auth_header = create_authorization_header(
                request_body=json.dumps(data),
                path='/notifications/email',
                method='POST',
                service_id=service.id
            )

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
                                   sample_email_template,
                                   sample_notification):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:

            sample_service.message_limit = 1
            notify_db.session.add(sample_service)
            notify_db.session.commit()

            data = {
                'to': 'ok@ok.com',
                'template': str(sample_email_template.id)
            }

            auth_header = create_authorization_header(
                request_body=json.dumps(data),
                path='/notifications/email',
                method='POST',
                service_id=sample_service.id
            )

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

            auth_header = create_authorization_header(
                request_body=json.dumps(data),
                path='/notifications/sms',
                method='POST',
                service_id=service.id
            )

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

            auth_header = create_authorization_header(
                request_body=json.dumps(data),
                path='/notifications/sms',
                method='POST',
                service_id=service.id
            )

            response = client.post(
                path='/notifications/sms',
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            assert response.status_code == 201


def test_firetext_callback_should_not_need_auth(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            response = client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=0&reference=send-sms-code&time=2016-03-10 14:17:00',
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            assert response.status_code == 200


def test_firetext_callback_should_return_400_if_empty_reference(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            response = client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=0&reference=&time=2016-03-10 14:17:00',
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 400
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == ['Firetext callback failed: reference missing']


def test_firetext_callback_should_return_400_if_no_reference(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            response = client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=0&time=2016-03-10 14:17:00',
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 400
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == ['Firetext callback failed: reference missing']


def test_firetext_callback_should_return_200_if_send_sms_reference(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            response = client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=0&time=2016-03-10 14:17:00&reference=send-sms-code',
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 200
            assert json_resp['result'] == 'success'
            assert json_resp['message'] == 'Firetext callback succeeded: send-sms-code'


def test_firetext_callback_should_return_400_if_no_status(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            response = client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&time=2016-03-10 14:17:00&reference=send-sms-code',
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 400
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == ['Firetext callback failed: status missing']


def test_firetext_callback_should_return_400_if_unknown_status(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            response = client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=99&time=2016-03-10 14:17:00&reference={}'.format(uuid.uuid4()),
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 400
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == 'Firetext callback failed: status 99 not found.'


def test_firetext_callback_should_return_400_if_invalid_guid_notification_id(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            response = client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=0&time=2016-03-10 14:17:00&reference=1234',
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 400
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == 'Firetext callback with invalid reference 1234'


def test_firetext_callback_should_return_404_if_cannot_find_notification_id(notify_db, notify_db_session, notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            missing_notification_id = uuid.uuid4()
            response = client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=0&time=2016-03-10 14:17:00&reference={}'.format(
                    missing_notification_id
                ),
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 400
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == 'Firetext callback failed: notification {} not found. Status {}'.format(
                missing_notification_id,
                'Delivered'
            )


def test_firetext_callback_should_update_notification_status(notify_api, sample_notification):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            original = get_notification_by_id(sample_notification.id)
            assert original.status == 'sending'

            response = client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=0&time=2016-03-10 14:17:00&reference={}'.format(
                    sample_notification.id
                ),
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 200
            assert json_resp['result'] == 'success'
            assert json_resp['message'] == 'Firetext callback succeeded. reference {} updated'.format(
                sample_notification.id
            )
            updated = get_notification_by_id(sample_notification.id)
            assert updated.status == 'delivered'
            assert get_notification_by_id(sample_notification.id).status == 'delivered'
            assert dao_get_notification_statistics_for_service(sample_notification.service_id)[0].sms_delivered == 1
            assert dao_get_notification_statistics_for_service(sample_notification.service_id)[0].sms_requested == 1
            assert dao_get_notification_statistics_for_service(sample_notification.service_id)[0].sms_failed == 0


def test_firetext_callback_should_update_notification_status_failed(notify_api, sample_notification):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            original = get_notification_by_id(sample_notification.id)
            assert original.status == 'sending'

            response = client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=1&time=2016-03-10 14:17:00&reference={}'.format(
                    sample_notification.id
                ),
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 200
            assert json_resp['result'] == 'success'
            assert json_resp['message'] == 'Firetext callback succeeded. reference {} updated'.format(
                sample_notification.id
            )
            updated = get_notification_by_id(sample_notification.id)
            assert updated.status == 'failed'
            assert dao_get_notification_statistics_for_service(sample_notification.service_id)[0].sms_delivered == 0
            assert dao_get_notification_statistics_for_service(sample_notification.service_id)[0].sms_requested == 1
            assert dao_get_notification_statistics_for_service(sample_notification.service_id)[0].sms_failed == 1


def test_firetext_callback_should_update_notification_status_sent(notify_api, notify_db, notify_db_session):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            notification = create_sample_notification(notify_db, notify_db_session, status='delivered')
            original = get_notification_by_id(notification.id)
            assert original.status == 'delivered'

            response = client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=2&time=2016-03-10 14:17:00&reference={}'.format(
                    notification.id
                ),
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            json_resp = json.loads(response.get_data(as_text=True))
            print(json_resp)
            assert response.status_code == 200
            assert json_resp['result'] == 'success'
            assert json_resp['message'] == 'Firetext callback succeeded. reference {} updated'.format(
                notification.id
            )
            updated = get_notification_by_id(notification.id)
            assert updated.status == 'delivered'
            assert dao_get_notification_statistics_for_service(notification.service_id)[0].sms_delivered == 1
            assert dao_get_notification_statistics_for_service(notification.service_id)[0].sms_requested == 1
            assert dao_get_notification_statistics_for_service(notification.service_id)[0].sms_failed == 0


def test_firetext_callback_should_update_multiple_notification_status_sent(notify_api, notify_db, notify_db_session):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            notification1 = create_sample_notification(notify_db, notify_db_session, status='delivered')
            notification2 = create_sample_notification(notify_db, notify_db_session, status='delivered')
            notification3 = create_sample_notification(notify_db, notify_db_session, status='delivered')

            client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=0&time=2016-03-10 14:17:00&reference={}'.format(
                    notification1.id
                ),
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=0&time=2016-03-10 14:17:00&reference={}'.format(
                    notification2.id
                ),
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=0&time=2016-03-10 14:17:00&reference={}'.format(
                    notification3.id
                ),
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            assert dao_get_notification_statistics_for_service(notification1.service_id)[0].sms_delivered == 3
            assert dao_get_notification_statistics_for_service(notification1.service_id)[0].sms_requested == 3
            assert dao_get_notification_statistics_for_service(notification1.service_id)[0].sms_failed == 0


def test_process_mmg_response_return_200_when_cid_is_send_sms_code(notify_api):
    with notify_api.test_request_context():
        data = json.dumps({"reference": "10100164",
                           "CID": "send-sms-code",
                           "MSISDN": "447775349060",
                           "status": "00",
                           "deliverytime": "2016-04-05 16:01:07"})

        with notify_api.test_client() as client:
            response = client.post(path='notifications/sms/mmg',
                                   data=data,
                                   headers=[('Content-Type', 'application/json')])
            assert response.status_code == 200
            json_data = json.loads(response.data)
            assert json_data['result'] == 'success'
            assert json_data['message'] == 'MMG callback succeeded: send-sms-code'


def test_process_mmg_response_returns_200_when_cid_is_valid_notification_id(notify_api, sample_notification):
    with notify_api.test_client() as client:
        data = json.dumps({"reference": "mmg_reference",
                           "CID": str(sample_notification.id),
                           "MSISDN": "447777349060",
                           "status": "00",
                           "deliverytime": "2016-04-05 16:01:07"})

        response = client.post(path='notifications/sms/mmg',
                               data=data,
                               headers=[('Content-Type', 'application/json')])
        assert response.status_code == 200
        json_data = json.loads(response.data)
        assert json_data['result'] == 'success'
        assert json_data['message'] == 'MMG callback succeeded. reference {} updated'.format(sample_notification.id)


def test_process_mmg_response_returns_400_for_malformed_data(notify_api):
    with notify_api.test_client() as client:
        data = json.dumps({"reference": "mmg_reference",
                           "monkey": 'random thing',
                           "MSISDN": "447777349060",
                           "no_status": "00",
                           "deliverytime": "2016-04-05 16:01:07"})

        response = client.post(path='notifications/sms/mmg',
                               data=data,
                               headers=[('Content-Type', 'application/json')])
        assert response.status_code == 400
        json_data = json.loads(response.data)
        assert json_data['result'] == 'error'
        assert len(json_data['message']) == 2
        assert "{} callback failed: {} missing".format('MMG', 'status') in json_data['message']
        assert "{} callback failed: {} missing".format('MMG', 'CID') in json_data['message']


def test_ses_callback_should_not_need_auth(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            response = client.post(
                path='/notifications/email/ses',
                data=ses_notification_callback(),
                headers=[('Content-Type', 'text/plain; charset=UTF-8')]
            )
            assert response.status_code == 404


def test_ses_callback_should_fail_if_invalid_json(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            response = client.post(
                path='/notifications/email/ses',
                data="nonsense",
                headers=[('Content-Type', 'text/plain; charset=UTF-8')]
            )
            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 400
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == 'SES callback failed: invalid json'


def test_ses_callback_should_fail_if_invalid_notification_type(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:

            response = client.post(
                path='/notifications/email/ses',
                data=ses_invalid_notification_type_callback(),
                headers=[('Content-Type', 'text/plain; charset=UTF-8')]
            )
            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 400
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == 'SES callback failed: status Unknown not found'


def test_ses_callback_should_fail_if_missing_message_id(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:

            response = client.post(
                path='/notifications/email/ses',
                data=ses_missing_notification_id_callback(),
                headers=[('Content-Type', 'text/plain; charset=UTF-8')]
            )
            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 400
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == 'SES callback failed: messageId missing'


def test_ses_callback_should_fail_if_notification_cannot_be_found(notify_db, notify_db_session, notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:

            response = client.post(
                path='/notifications/email/ses',
                data=ses_invalid_notification_id_callback(),
                headers=[('Content-Type', 'text/plain; charset=UTF-8')]
            )
            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 404
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == 'SES callback failed: notification not found. Status delivered'


def test_ses_callback_should_update_notification_status(
        notify_api,
        notify_db,
        notify_db_session,
        sample_email_template):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            notification = create_sample_notification(
                notify_db,
                notify_db_session,
                template=sample_email_template,
                reference='ref'
            )

            assert get_notification_by_id(notification.id).status == 'sending'

            response = client.post(
                path='/notifications/email/ses',
                data=ses_notification_callback(),
                headers=[('Content-Type', 'text/plain; charset=UTF-8')]
            )
            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 200
            assert json_resp['result'] == 'success'
            assert json_resp['message'] == 'SES callback succeeded'
            assert get_notification_by_id(notification.id).status == 'delivered'
            assert dao_get_notification_statistics_for_service(notification.service_id)[0].emails_delivered == 1
            assert dao_get_notification_statistics_for_service(notification.service_id)[0].emails_requested == 1
            assert dao_get_notification_statistics_for_service(notification.service_id)[0].emails_failed == 0


def test_ses_callback_should_update_multiple_notification_status_sent(
        notify_api,
        notify_db,
        notify_db_session,
        sample_email_template):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:

            notification1 = create_sample_notification(
                notify_db,
                notify_db_session,
                template=sample_email_template,
                reference='ref1',
                status='delivered')

            notification2 = create_sample_notification(
                notify_db,
                notify_db_session,
                template=sample_email_template,
                reference='ref2',
                status='delivered')

            notification3 = create_sample_notification(
                notify_db,
                notify_db_session,
                template=sample_email_template,
                reference='ref2',
                status='delivered')

            client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=0&time=2016-03-10 14:17:00&reference={}'.format(
                    notification1.id
                ),
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=0&time=2016-03-10 14:17:00&reference={}'.format(
                    notification2.id
                ),
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            client.post(
                path='/notifications/sms/firetext',
                data='mobile=441234123123&status=0&time=2016-03-10 14:17:00&reference={}'.format(
                    notification3.id
                ),
                headers=[('Content-Type', 'application/x-www-form-urlencoded')])

            assert dao_get_notification_statistics_for_service(notification1.service_id)[0].emails_delivered == 3
            assert dao_get_notification_statistics_for_service(notification1.service_id)[0].emails_requested == 3
            assert dao_get_notification_statistics_for_service(notification1.service_id)[0].emails_failed == 0


def test_should_handle_invite_email_callbacks(notify_api, notify_db, notify_db_session):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:

            notify_api.config['INVITATION_EMAIL_FROM'] = 'test-invite'
            notify_api.config['NOTIFY_EMAIL_DOMAIN'] = 'test-domain.com'

            response = client.post(
                path='/notifications/email/ses',
                data=ses_invite_callback(),
                headers=[('Content-Type', 'text/plain; charset=UTF-8')]
            )
            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 200
            assert json_resp['result'] == 'success'
            assert json_resp['message'] == 'SES callback succeeded'


def test_should_handle_validation_code_callbacks(notify_api, notify_db, notify_db_session):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:

            notify_api.config['VERIFY_CODE_FROM_EMAIL_ADDRESS'] = 'valid-code@test.com'

            response = client.post(
                path='/notifications/email/ses',
                data=ses_validation_code_callback(),
                headers=[('Content-Type', 'text/plain; charset=UTF-8')]
            )
            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 200
            assert json_resp['result'] == 'success'
            assert json_resp['message'] == 'SES callback succeeded'


def ses_validation_code_callback():
    return b'{\n  "Type" : "Notification",\n  "MessageId" : "ref",\n  "TopicArn" : "arn:aws:sns:eu-west-1:123456789012:testing",\n  "Message" : "{\\"notificationType\\":\\"Delivery\\",\\"mail\\":{\\"timestamp\\":\\"2016-03-14T12:35:25.909Z\\",\\"source\\":\\"valid-code@test.com\\",\\"sourceArn\\":\\"arn:aws:ses:eu-west-1:123456789012:identity/testing-notify\\",\\"sendingAccountId\\":\\"123456789012\\",\\"messageId\\":\\"ref\\",\\"destination\\":[\\"testing@digital.cabinet-office.gov.uk\\"]},\\"delivery\\":{\\"timestamp\\":\\"2016-03-14T12:35:26.567Z\\",\\"processingTimeMillis\\":658,\\"recipients\\":[\\"testing@digital.cabinet-office.gov.u\\"],\\"smtpResponse\\":\\"250 2.0.0 OK 1457958926 uo5si26480932wjc.221 - gsmtp\\",\\"reportingMTA\\":\\"a6-238.smtp-out.eu-west-1.amazonses.com\\"}}",\n  "Timestamp" : "2016-03-14T12:35:26.665Z",\n  "SignatureVersion" : "1",\n  "Signature" : "X8d7eTAOZ6wlnrdVVPYanrAlsX0SMPfOzhoTEBnQqYkrNWTqQY91C0f3bxtPdUhUtOowyPAOkTQ4KnZuzphfhVb2p1MyVYMxNKcBFB05/qaCX99+92fjw4x9LeUOwyGwMv5F0Vkfi5qZCcEw69uVrhYLVSTFTrzi/yCtru+yFULMQ6UhbY09GwiP6hjxZMVr8aROQy5lLHglqQzOuSZ4KeD85JjifHdKzlx8jjQ+uj+FLzHXPMAPmPU1JK9kpoHZ1oPshAFgPDpphJe+HwcJ8ezmk+3AEUr3wWli3xF+49y8Z2anASSVp6YI2YP95UT8Rlh3qT3T+V9V8rbSVislxA==",\n  "SigningCertURL" : "https://sns.eu-west-1.amazonaws.com/SimpleNotificationService-bb750dd426d95ee9390147a5624348ee.pem",\n  "UnsubscribeURL" : "https://sns.eu-west-1.amazonaws.com/?Action=Unsubscribe&SubscriptionArn=arn:aws:sns:eu-west-1:302763885840:preview-emails:d6aad3ef-83d6-4cf3-a470-54e2e75916da"\n}'  # noqa


def ses_invite_callback():
    return b'{\n  "Type" : "Notification",\n  "MessageId" : "ref",\n  "TopicArn" : "arn:aws:sns:eu-west-1:123456789012:testing",\n  "Message" : "{\\"notificationType\\":\\"Delivery\\",\\"mail\\":{\\"timestamp\\":\\"2016-03-14T12:35:25.909Z\\",\\"source\\":\\"test-invite@test-domain.com\\",\\"sourceArn\\":\\"arn:aws:ses:eu-west-1:123456789012:identity/testing-notify\\",\\"sendingAccountId\\":\\"123456789012\\",\\"messageId\\":\\"ref\\",\\"destination\\":[\\"testing@digital.cabinet-office.gov.uk\\"]},\\"delivery\\":{\\"timestamp\\":\\"2016-03-14T12:35:26.567Z\\",\\"processingTimeMillis\\":658,\\"recipients\\":[\\"testing@digital.cabinet-office.gov.u\\"],\\"smtpResponse\\":\\"250 2.0.0 OK 1457958926 uo5si26480932wjc.221 - gsmtp\\",\\"reportingMTA\\":\\"a6-238.smtp-out.eu-west-1.amazonses.com\\"}}",\n  "Timestamp" : "2016-03-14T12:35:26.665Z",\n  "SignatureVersion" : "1",\n  "Signature" : "X8d7eTAOZ6wlnrdVVPYanrAlsX0SMPfOzhoTEBnQqYkrNWTqQY91C0f3bxtPdUhUtOowyPAOkTQ4KnZuzphfhVb2p1MyVYMxNKcBFB05/qaCX99+92fjw4x9LeUOwyGwMv5F0Vkfi5qZCcEw69uVrhYLVSTFTrzi/yCtru+yFULMQ6UhbY09GwiP6hjxZMVr8aROQy5lLHglqQzOuSZ4KeD85JjifHdKzlx8jjQ+uj+FLzHXPMAPmPU1JK9kpoHZ1oPshAFgPDpphJe+HwcJ8ezmk+3AEUr3wWli3xF+49y8Z2anASSVp6YI2YP95UT8Rlh3qT3T+V9V8rbSVislxA==",\n  "SigningCertURL" : "https://sns.eu-west-1.amazonaws.com/SimpleNotificationService-bb750dd426d95ee9390147a5624348ee.pem",\n  "UnsubscribeURL" : "https://sns.eu-west-1.amazonaws.com/?Action=Unsubscribe&SubscriptionArn=arn:aws:sns:eu-west-1:302763885840:preview-emails:d6aad3ef-83d6-4cf3-a470-54e2e75916da"\n}'  # noqa


def ses_notification_callback():
    return b'{\n  "Type" : "Notification",\n  "MessageId" : "ref",\n  "TopicArn" : "arn:aws:sns:eu-west-1:123456789012:testing",\n  "Message" : "{\\"notificationType\\":\\"Delivery\\",\\"mail\\":{\\"timestamp\\":\\"2016-03-14T12:35:25.909Z\\",\\"source\\":\\"test@test-domain.com\\",\\"sourceArn\\":\\"arn:aws:ses:eu-west-1:123456789012:identity/testing-notify\\",\\"sendingAccountId\\":\\"123456789012\\",\\"messageId\\":\\"ref\\",\\"destination\\":[\\"testing@digital.cabinet-office.gov.uk\\"]},\\"delivery\\":{\\"timestamp\\":\\"2016-03-14T12:35:26.567Z\\",\\"processingTimeMillis\\":658,\\"recipients\\":[\\"testing@digital.cabinet-office.gov.uk\\"],\\"smtpResponse\\":\\"250 2.0.0 OK 1457958926 uo5si26480932wjc.221 - gsmtp\\",\\"reportingMTA\\":\\"a6-238.smtp-out.eu-west-1.amazonses.com\\"}}",\n  "Timestamp" : "2016-03-14T12:35:26.665Z",\n  "SignatureVersion" : "1",\n  "Signature" : "X8d7eTAOZ6wlnrdVVPYanrAlsX0SMPfOzhoTEBnQqYkrNWTqQY91C0f3bxtPdUhUtOowyPAOkTQ4KnZuzphfhVb2p1MyVYMxNKcBFB05/qaCX99+92fjw4x9LeUOwyGwMv5F0Vkfi5qZCcEw69uVrhYLVSTFTrzi/yCtru+yFULMQ6UhbY09GwiP6hjxZMVr8aROQy5lLHglqQzOuSZ4KeD85JjifHdKzlx8jjQ+uj+FLzHXPMAPmPU1JK9kpoHZ1oPshAFgPDpphJe+HwcJ8ezmk+3AEUr3wWli3xF+49y8Z2anASSVp6YI2YP95UT8Rlh3qT3T+V9V8rbSVislxA==",\n  "SigningCertURL" : "https://sns.eu-west-1.amazonaws.com/SimpleNotificationService-bb750dd426d95ee9390147a5624348ee.pem",\n  "UnsubscribeURL" : "https://sns.eu-west-1.amazonaws.com/?Action=Unsubscribe&SubscriptionArn=arn:aws:sns:eu-west-1:302763885840:preview-emails:d6aad3ef-83d6-4cf3-a470-54e2e75916da"\n}'  # noqa


def ses_invalid_notification_id_callback():
    return b'{\n  "Type" : "Notification",\n  "MessageId" : "missing",\n  "TopicArn" : "arn:aws:sns:eu-west-1:123456789012:testing",\n  "Message" : "{\\"notificationType\\":\\"Delivery\\",\\"mail\\":{\\"timestamp\\":\\"2016-03-14T12:35:25.909Z\\",\\"source\\":\\"test@test-domain.com\\",\\"sourceArn\\":\\"arn:aws:ses:eu-west-1:123456789012:identity/testing-notify\\",\\"sendingAccountId\\":\\"123456789012\\",\\"messageId\\":\\"missing\\",\\"destination\\":[\\"testing@digital.cabinet-office.gov.uk\\"]},\\"delivery\\":{\\"timestamp\\":\\"2016-03-14T12:35:26.567Z\\",\\"processingTimeMillis\\":658,\\"recipients\\":[\\"testing@digital.cabinet-office.gov.uk\\"],\\"smtpResponse\\":\\"250 2.0.0 OK 1457958926 uo5si26480932wjc.221 - gsmtp\\",\\"reportingMTA\\":\\"a6-238.smtp-out.eu-west-1.amazonses.com\\"}}",\n  "Timestamp" : "2016-03-14T12:35:26.665Z",\n  "SignatureVersion" : "1",\n  "Signature" : "X8d7eTAOZ6wlnrdVVPYanrAlsX0SMPfOzhoTEBnQqYkrNWTqQY91C0f3bxtPdUhUtOowyPAOkTQ4KnZuzphfhVb2p1MyVYMxNKcBFB05/qaCX99+92fjw4x9LeUOwyGwMv5F0Vkfi5qZCcEw69uVrhYLVSTFTrzi/yCtru+yFULMQ6UhbY09GwiP6hjxZMVr8aROQy5lLHglqQzOuSZ4KeD85JjifHdKzlx8jjQ+uj+FLzHXPMAPmPU1JK9kpoHZ1oPshAFgPDpphJe+HwcJ8ezmk+3AEUr3wWli3xF+49y8Z2anASSVp6YI2YP95UT8Rlh3qT3T+V9V8rbSVislxA==",\n  "SigningCertURL" : "https://sns.eu-west-1.amazonaws.com/SimpleNotificationService-bb750dd426d95ee9390147a5624348ee.pem",\n  "UnsubscribeURL" : "https://sns.eu-west-1.amazonaws.com/?Action=Unsubscribe&SubscriptionArn=arn:aws:sns:eu-west-1:302763885840:preview-emails:d6aad3ef-83d6-4cf3-a470-54e2e75916da"\n}'  # noqa


def ses_missing_notification_id_callback():
    return b'{\n  "Type" : "Notification",\n  "TopicArn" : "arn:aws:sns:eu-west-1:123456789012:testing",\n  "Message" : "{\\"notificationType\\":\\"Delivery\\",\\"mail\\":{\\"timestamp\\":\\"2016-03-14T12:35:25.909Z\\",\\"source\\":\\"test@test-domain.com\\",\\"sourceArn\\":\\"arn:aws:ses:eu-west-1:123456789012:identity/testing-notify\\",\\"sendingAccountId\\":\\"123456789012\\",\\"destination\\":[\\"testing@digital.cabinet-office.gov.uk\\"]},\\"delivery\\":{\\"timestamp\\":\\"2016-03-14T12:35:26.567Z\\",\\"processingTimeMillis\\":658,\\"recipients\\":[\\"testing@digital.cabinet-office.gov.uk\\"],\\"smtpResponse\\":\\"250 2.0.0 OK 1457958926 uo5si26480932wjc.221 - gsmtp\\",\\"reportingMTA\\":\\"a6-238.smtp-out.eu-west-1.amazonses.com\\"}}",\n  "Timestamp" : "2016-03-14T12:35:26.665Z",\n  "SignatureVersion" : "1",\n  "Signature" : "X8d7eTAOZ6wlnrdVVPYanrAlsX0SMPfOzhoTEBnQqYkrNWTqQY91C0f3bxtPdUhUtOowyPAOkTQ4KnZuzphfhVb2p1MyVYMxNKcBFB05/qaCX99+92fjw4x9LeUOwyGwMv5F0Vkfi5qZCcEw69uVrhYLVSTFTrzi/yCtru+yFULMQ6UhbY09GwiP6hjxZMVr8aROQy5lLHglqQzOuSZ4KeD85JjifHdKzlx8jjQ+uj+FLzHXPMAPmPU1JK9kpoHZ1oPshAFgPDpphJe+HwcJ8ezmk+3AEUr3wWli3xF+49y8Z2anASSVp6YI2YP95UT8Rlh3qT3T+V9V8rbSVislxA==",\n  "SigningCertURL" : "https://sns.eu-west-1.amazonaws.com/SimpleNotificationService-bb750dd426d95ee9390147a5624348ee.pem",\n  "UnsubscribeURL" : "https://sns.eu-west-1.amazonaws.com/?Action=Unsubscribe&SubscriptionArn=arn:aws:sns:eu-west-1:302763885840:preview-emails:d6aad3ef-83d6-4cf3-a470-54e2e75916da"\n}'  # noqa


def ses_invalid_notification_type_callback():
    return b'{\n  "Type" : "Notification",\n  "TopicArn" : "arn:aws:sns:eu-west-1:123456789012:testing",\n  "Message" : "{\\"notificationType\\":\\"Unknown\\",\\"mail\\":{\\"timestamp\\":\\"2016-03-14T12:35:25.909Z\\",\\"source\\":\\"test@test-domain.com\\",\\"sourceArn\\":\\"arn:aws:ses:eu-west-1:123456789012:identity/testing-notify\\",\\"sendingAccountId\\":\\"123456789012\\",\\"destination\\":[\\"testing@digital.cabinet-office.gov.uk\\"]},\\"delivery\\":{\\"timestamp\\":\\"2016-03-14T12:35:26.567Z\\",\\"processingTimeMillis\\":658,\\"recipients\\":[\\"testing@digital.cabinet-office.gov.uk\\"],\\"smtpResponse\\":\\"250 2.0.0 OK 1457958926 uo5si26480932wjc.221 - gsmtp\\",\\"reportingMTA\\":\\"a6-238.smtp-out.eu-west-1.amazonses.com\\"}}",\n  "Timestamp" : "2016-03-14T12:35:26.665Z",\n  "SignatureVersion" : "1",\n  "Signature" : "X8d7eTAOZ6wlnrdVVPYanrAlsX0SMPfOzhoTEBnQqYkrNWTqQY91C0f3bxtPdUhUtOowyPAOkTQ4KnZuzphfhVb2p1MyVYMxNKcBFB05/qaCX99+92fjw4x9LeUOwyGwMv5F0Vkfi5qZCcEw69uVrhYLVSTFTrzi/yCtru+yFULMQ6UhbY09GwiP6hjxZMVr8aROQy5lLHglqQzOuSZ4KeD85JjifHdKzlx8jjQ+uj+FLzHXPMAPmPU1JK9kpoHZ1oPshAFgPDpphJe+HwcJ8ezmk+3AEUr3wWli3xF+49y8Z2anASSVp6YI2YP95UT8Rlh3qT3T+V9V8rbSVislxA==",\n  "SigningCertURL" : "https://sns.eu-west-1.amazonaws.com/SimpleNotificationService-bb750dd426d95ee9390147a5624348ee.pem",\n  "UnsubscribeURL" : "https://sns.eu-west-1.amazonaws.com/?Action=Unsubscribe&SubscriptionArn=arn:aws:sns:eu-west-1:302763885840:preview-emails:d6aad3ef-83d6-4cf3-a470-54e2e75916da"\n}'  # noqa
