import boto3
import moto

from tests import create_authorization_header
from flask import url_for, json
from app import notify_alpha_client
from app.models import Service


def test_get_notifications(
        notify_api, notify_db, notify_db_session, sample_service, sample_admin_service_id, mocker):
    """
    Tests GET endpoint '/' to retrieve entire service list.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch(
                'app.notify_alpha_client.fetch_notification_by_id',
                return_value={
                    'notifications': [
                        {
                            'id': 'my_id',
                            'notification': 'some notify'
                        }
                    ]
                }
            )

            auth_header = create_authorization_header(
                service_id=sample_admin_service_id,
                path=url_for('notifications.get_notifications', notification_id=123),
                method='GET')

            response = client.get(
                url_for('notifications.get_notifications', notification_id=123),
                headers=[auth_header])

            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 200
            assert len(json_resp['notifications']) == 1
            assert json_resp['notifications'][0]['id'] == 'my_id'
            assert json_resp['notifications'][0]['notification'] == 'some notify'
            notify_alpha_client.fetch_notification_by_id.assert_called_with("123")


def test_get_notifications_empty_result(
        notify_api, notify_db, notify_db_session, sample_service, sample_admin_service_id, mocker):
    """
    Tests GET endpoint '/' to retrieve entire service list.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch(
                'app.notify_alpha_client.fetch_notification_by_id',
                return_value={
                    'notifications': [
                    ]
                }
            )

            auth_header = create_authorization_header(
                service_id=sample_admin_service_id,
                path=url_for('notifications.get_notifications', notification_id=123),
                method='GET')

            response = client.get(
                url_for('notifications.get_notifications', notification_id=123),
                headers=[auth_header])

            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 200
            assert len(json_resp['notifications']) == 0
            notify_alpha_client.fetch_notification_by_id.assert_called_with("123")


@moto.mock_sqs
def test_should_reject_if_no_phone_numbers(
        notify_api, notify_db, notify_db_session, sample_service, sample_admin_service_id, mocker):
    """
    Tests GET endpoint '/' to retrieve entire service list.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            set_up_mock_queue()
            mocker.patch(
                'app.notify_alpha_client.send_sms',
                return_value='success'
            )
            data = {
                'notification': {
                    'template': "my message"
                }
            }
            auth_header = create_authorization_header(
                service_id=sample_admin_service_id,
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
            assert 'Required data missing' in json_resp['message']['to'][0]
            assert not notify_alpha_client.send_sms.called


@moto.mock_sqs
def test_should_reject_bad_phone_numbers(
        notify_api, notify_db, notify_db_session, sample_service, sample_admin_service_id, mocker):
    """
    Tests GET endpoint '/' to retrieve entire service list.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            set_up_mock_queue()
            mocker.patch(
                'app.notify_alpha_client.send_sms',
                return_value='success'
            )
            data = {
                'notification': {
                    'to': 'invalid',
                    'template': "my message"
                }
            }
            auth_header = create_authorization_header(
                service_id=sample_admin_service_id,
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
            assert 'invalid phone number, must be of format +441234123123' in json_resp['message']['to']
            assert not notify_alpha_client.send_sms.called


@moto.mock_sqs
def test_should_reject_missing_template(
        notify_api, notify_db, notify_db_session, sample_service, sample_admin_service_id, mocker):
    """
    Tests GET endpoint '/' to retrieve entire service list.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            set_up_mock_queue()
            mocker.patch(
                'app.notify_alpha_client.send_sms',
                return_value='success'
            )
            data = {
                'notification': {
                    'to': '+441234123123'
                }
            }
            auth_header = create_authorization_header(
                service_id=sample_admin_service_id,
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
            assert 'Required data missing' in json_resp['message']['template']
            assert not notify_alpha_client.send_sms.called


@moto.mock_sqs
def test_send_template_content(notify_api,
                               notify_db,
                               notify_db_session,
                               sample_api_key,
                               sample_template,
                               sample_user,
                               mocker):
    """
    Test POST endpoint '/sms' with service notification.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            set_up_mock_queue()
            mocker.patch(
                'app.notify_alpha_client.send_sms',
                return_value={
                    "notification": {
                        "createdAt": "2015-11-03T09:37:27.414363Z",
                        "id": 100,
                        "jobId": 65,
                        "message": sample_template.content,
                        "method": "sms",
                        "status": "created",
                        "to": sample_user.mobile_number
                    }
                }
            )
            data = {
                'notification': {
                    'to': sample_user.mobile_number,
                    'template': sample_template.id
                }
            }
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
            assert response.status_code == 200
            assert json_resp['notification']['id'] == 100
            notify_alpha_client.send_sms.assert_called_with(
                mobile_number=sample_user.mobile_number,
                message=sample_template.content)


@moto.mock_sqs
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
            set_up_mock_queue()
            Service.query.filter_by(
                id=sample_template.service.id).update({'restricted': True})
            invalid_mob = '+449999999999'
            mocker.patch(
                'app.notify_alpha_client.send_sms',
                return_value={}
            )
            data = {
                'notification': {
                    'to': invalid_mob,
                    'template': sample_template.id
                }
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
            assert 'Invalid phone number for restricted service' in json_resp['message']['to']


@moto.mock_sqs
def test_should_allow_valid_message(
        notify_api, notify_db, notify_db_session, sample_service, mocker):
    """
    Tests POST endpoint '/sms' with notifications-admin notification.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            set_up_mock_queue()
            mocker.patch(
                'app.notify_alpha_client.send_sms',
                return_value={
                    "notification": {
                        "createdAt": "2015-11-03T09:37:27.414363Z",
                        "id": 100,
                        "jobId": 65,
                        "message": "This is the message",
                        "method": "sms",
                        "status": "created",
                        "to": "+449999999999"
                    }
                }
            )
            data = {
                'notification': {
                    'to': '+441234123123',
                    'template': 'valid'
                }
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
            assert response.status_code == 200
            assert json_resp['notification']['id'] == 100
            notify_alpha_client.send_sms.assert_called_with(mobile_number='+441234123123', message="valid")


def test_send_email_valid_data(notify_api,
                               notify_db,
                               notify_db_session,
                               sample_service,
                               sample_admin_service_id,
                               mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            to_address = "to@notify.com"
            from_address = "from@notify.com"
            subject = "This is the subject"
            message = "This is the message"
            mocker.patch(
                'app.notify_alpha_client.send_email',
                return_value={
                    "notification": {
                        "createdAt": "2015-11-03T09:37:27.414363Z",
                        "id": 100,
                        "jobId": 65,
                        "subject": subject,
                        "message": message,
                        "method": "email",
                        "status": "created",
                        "to": to_address,
                        "from": from_address
                    }
                }
            )
            data = {
                'notification': {
                    'to': to_address,
                    'from': from_address,
                    'subject': subject,
                    'message': message
                }
            }
            auth_header = create_authorization_header(
                request_body=json.dumps(data),
                path=url_for('notifications.create_email_notification'),
                method='POST')

            response = client.post(
                url_for('notifications.create_email_notification'),
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])

            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 200
            assert json_resp['notification']['id'] == 100
            notify_alpha_client.send_email.assert_called_with(
                to_address, message, from_address, subject)


@moto.mock_sqs
def test_add_notification_to_queue(notify_api, notify_db, notify_db_session, sample_service):
    set_up_mock_queue()
    from app.notifications.rest import _add_notification_to_queue
    _add_notification_to_queue('some message', sample_service, 'sms', '+447515349060')


def set_up_mock_queue():
    # set up mock queue
    boto3.setup_default_session(region_name='eu-west-1')
    conn = boto3.resource('sqs')
