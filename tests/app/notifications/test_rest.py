from tests import create_authorization_header
from flask import url_for, json
from app import notify_alpha_client


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


def test_should_reject_if_no_phone_numbers(
        notify_api, notify_db, notify_db_session, sample_service, sample_admin_service_id, mocker):
    """
    Tests GET endpoint '/' to retrieve entire service list.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch(
                'app.notify_alpha_client.send_sms',
                return_value='success'
            )
            data = {
                'notification': {
                    'message': "my message"
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
            print(json_resp)
            assert response.status_code == 400
            assert json_resp['result'] == 'error'
            assert len(json_resp['message']) == 1
            assert len(json_resp['message']['to']) == 1
            assert json_resp['message']['to'][0] == 'required'
            assert not notify_alpha_client.send_sms.called


def test_should_reject_bad_phone_numbers(
        notify_api, notify_db, notify_db_session, sample_service, sample_admin_service_id, mocker):
    """
    Tests GET endpoint '/' to retrieve entire service list.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch(
                'app.notify_alpha_client.send_sms',
                return_value='success'
            )
            data = {
                'notification': {
                    'to': 'invalid',
                    'message': "my message"
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
            print(json_resp)
            assert response.status_code == 400
            assert json_resp['result'] == 'error'
            assert len(json_resp['message']) == 1
            assert len(json_resp['message']['to']) == 1
            assert json_resp['message']['to'][0] == 'invalid phone number, must be of format +441234123123'
            assert not notify_alpha_client.send_sms.called


def test_should_reject_missing_message(
        notify_api, notify_db, notify_db_session, sample_service, sample_admin_service_id, mocker):
    """
    Tests GET endpoint '/' to retrieve entire service list.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
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
            assert len(json_resp['message']) == 1
            assert len(json_resp['message']['message']) == 1
            assert json_resp['message']['message'][0] == 'required'
            assert not notify_alpha_client.send_sms.called


def test_should_reject_too_short_message(
        notify_api, notify_db, notify_db_session, sample_service, sample_admin_service_id, mocker):
    """
    Tests GET endpoint '/' to retrieve entire service list.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch(
                'app.notify_alpha_client.send_sms',
                return_value='success'
            )
            data = {
                'notification': {
                    'to': '+441234123123',
                    'message': ''
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
            assert len(json_resp['message']) == 1
            assert len(json_resp['message']['message']) == 1
            assert json_resp['message']['message'][0] == 'Invalid length. [1 - 160]'
            assert not notify_alpha_client.send_sms.called


def test_should_reject_too_long_message(
        notify_api, notify_db, notify_db_session, sample_service, sample_admin_service_id, mocker):
    """
    Tests GET endpoint '/' to retrieve entire service list.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch(
                'app.notify_alpha_client.send_sms',
                return_value='success'
            )
            data = {
                'notification': {
                    'to': '+441234123123',
                    'message': '1' * 161
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
            assert len(json_resp['message']) == 1
            assert len(json_resp['message']['message']) == 1
            assert json_resp['message']['message'][0] == 'Invalid length. [1 - 160]'
            assert not notify_alpha_client.send_sms.called


def test_should_allow_valid_message(
        notify_api, notify_db, notify_db_session, sample_service, sample_admin_service_id, mocker):
    """
    Tests GET endpoint '/' to retrieve entire service list.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
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
                    'message': 'valid'
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
            assert response.status_code == 200
            assert json_resp['notification']['id'] == 100
            notify_alpha_client.send_sms.assert_called_with(mobile_number='+441234123123', message='valid')


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
                service_id=sample_admin_service_id,
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
