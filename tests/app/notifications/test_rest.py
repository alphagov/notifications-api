import moto
import uuid

from tests import create_authorization_header
from flask import url_for, json
from app import notify_alpha_client
from app.models import Service


def test_get_notifications(
        notify_api, notify_db, notify_db_session, sample_api_key, mocker):
    """
    Tests GET endpoint '/' to retrieve entire service list.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header(
                service_id=sample_api_key.service_id,
                path=url_for('notifications.get_notifications', notification_id=123),
                method='GET')

            response = client.get(
                url_for('notifications.get_notifications', notification_id=123),
                headers=[auth_header])

            assert response.status_code == 200


def test_get_notifications_empty_result(
        notify_api, notify_db, notify_db_session, sample_api_key, mocker):
    """
    Tests GET endpoint '/' to retrieve entire service list.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header(
                service_id=sample_api_key.service_id,
                path=url_for('notifications.get_notifications', notification_id=123),
                method='GET')

            response = client.get(
                url_for('notifications.get_notifications', notification_id=123),
                headers=[auth_header])

            assert response.status_code == 200


def test_create_sms_should_reject_if_no_phone_numbers(
        notify_api, notify_db, notify_db_session, sample_api_key, mocker):
    """
    Tests GET endpoint '/' to retrieve entire service list.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'template': "my message"
            }
            auth_header = create_authorization_header(
                service_id=sample_api_key.service_id,
                request_body=json.dumps(data),
                path=url_for('notifications.create_sms_notification'),
                method='POST')

            response = client.post(
                url_for('notifications.create_sms_notification'),
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 400
            assert json_resp['result'] == 'error'
            assert 'Missing data for required field.' in json_resp['message']['to'][0]


def test_should_reject_bad_phone_numbers(
        notify_api, notify_db, notify_db_session, mocker):
    """
    Tests GET endpoint '/' to retrieve entire service list.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'to': 'invalid',
                'template': "my message"
            }
            auth_header = create_authorization_header(
                request_body=json.dumps(data),
                path=url_for('notifications.create_sms_notification'),
                method='POST')

            response = client.post(
                url_for('notifications.create_sms_notification'),
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 400
            assert json_resp['result'] == 'error'
            assert 'Invalid phone number, must be of format +441234123123' in json_resp['message']['to']


def test_send_notification_restrict_mobile(notify_api,
                                           notify_db,
                                           notify_db_session,
                                           sample_api_key,
                                           sample_template,
                                           sample_user,
                                           mocker):
    """
    Test POST endpoint '/sms' with service notification with mobile number
    not in restricted list.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            Service.query.filter_by(
                id=sample_template.service.id).update({'restricted': True})
            invalid_mob = '+449999999999'
            data = {
                'to': invalid_mob,
                'template': sample_template.id
            }
            assert invalid_mob != sample_user.mobile_number
            auth_header = create_authorization_header(
                service_id=sample_template.service.id,
                request_body=json.dumps(data),
                path=url_for('notifications.create_sms_notification'),
                method='POST')

            response = client.post(
                url_for('notifications.create_sms_notification'),
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 400
            assert 'Invalid phone number for restricted service' in json_resp['message']['restricted']


def test_send_notification_invalid_template_id(notify_api,
                                               notify_db,
                                               notify_db_session,
                                               sample_api_key,
                                               sample_template,
                                               sample_user,
                                               mocker):
    """
    Tests POST endpoint '/sms' with notifications-admin notification with invalid template id
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:

            Service.query.filter_by(
                id=sample_template.service.id).update({'restricted': True})
            invalid_mob = '+449999999999'
            data = {
                'to': invalid_mob,
                'template': 9999
            }
            assert invalid_mob != sample_user.mobile_number
            auth_header = create_authorization_header(
                service_id=sample_template.service.id,
                request_body=json.dumps(data),
                path=url_for('notifications.create_sms_notification'),
                method='POST')

            response = client.post(
                url_for('notifications.create_sms_notification'),
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 400
            assert 'Template not found' in json_resp['message']['template']


@moto.mock_sqs
def test_should_allow_valid_message(notify_api,
                                    notify_db,
                                    notify_db_session,
                                    sqs_client_conn,
                                    sample_user,
                                    sample_template,
                                    mocker):
    """
    Tests POST endpoint '/sms' with notifications-admin notification.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'to': '+441234123123',
                'template': sample_template.id
            }
            auth_header = create_authorization_header(
                request_body=json.dumps(data),
                path=url_for('notifications.create_sms_notification'),
                method='POST')

            response = client.post(
                url_for('notifications.create_sms_notification'),
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            assert response.status_code == 204


@moto.mock_sqs
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
                path=url_for('notifications.create_email_notification'),
                method='POST')

            response = client.post(
                url_for('notifications.create_email_notification'),
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            assert response.status_code == 204


@moto.mock_sqs
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
            url = url_for('notifications.create_sms_for_service', service_id=service_id)
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

            assert response.status_code == 204


@moto.mock_sqs
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

            url = url_for('notifications.create_sms_for_service', service_id=invalid_service_id)

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
