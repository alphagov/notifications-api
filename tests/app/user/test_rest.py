import json

from flask import url_for, current_app
from freezegun import freeze_time

import app
from app.models import (User, Permission, MANAGE_SETTINGS, MANAGE_TEMPLATES)
from app.dao.permissions_dao import default_service_permissions
from app.utils import url_with_token
from tests import create_authorization_header


def test_get_user_list(notify_api, notify_db, notify_db_session, sample_service):
    """
    Tests GET endpoint '/' to retrieve entire user list.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            header = create_authorization_header()
            response = client.get(url_for('user.get_user'),
                                  headers=[header])
            assert response.status_code == 200
            json_resp = json.loads(response.get_data(as_text=True))
            assert len(json_resp['data']) == 1
            sample_user = sample_service.users[0]
            expected_permissions = default_service_permissions
            fetched = json_resp['data'][0]

            assert str(sample_user.id) == fetched['id']
            assert sample_user.name == fetched['name']
            assert sample_user.mobile_number == fetched['mobile_number']
            assert sample_user.email_address == fetched['email_address']
            assert sample_user.state == fetched['state']
            assert sorted(expected_permissions) == sorted(fetched['permissions'][str(sample_service.id)])


def test_get_user(notify_api, notify_db, notify_db_session, sample_service):
    """
    Tests GET endpoint '/<user_id>' to retrieve a single service.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            sample_user = sample_service.users[0]
            header = create_authorization_header()
            resp = client.get(url_for('user.get_user',
                                      user_id=sample_user.id),
                              headers=[header])
            assert resp.status_code == 200
            json_resp = json.loads(resp.get_data(as_text=True))

            expected_permissions = default_service_permissions
            fetched = json_resp['data']

            assert str(sample_user.id) == fetched['id']
            assert sample_user.name == fetched['name']
            assert sample_user.mobile_number == fetched['mobile_number']
            assert sample_user.email_address == fetched['email_address']
            assert sample_user.state == fetched['state']
            assert sorted(expected_permissions) == sorted(fetched['permissions'][str(sample_service.id)])


def test_post_user(notify_api, notify_db, notify_db_session):
    """
    Tests POST endpoint '/' to create a user.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            assert User.query.count() == 0
            data = {
                "name": "Test User",
                "email_address": "user@digital.cabinet-office.gov.uk",
                "password": "password",
                "mobile_number": "+447700900986",
                "logged_in_at": None,
                "state": "active",
                "failed_login_count": 0,
                "permissions": {}
            }
            auth_header = create_authorization_header()
            headers = [('Content-Type', 'application/json'), auth_header]
            resp = client.post(
                url_for('user.create_user'),
                data=json.dumps(data),
                headers=headers)
            assert resp.status_code == 201
            user = User.query.filter_by(email_address='user@digital.cabinet-office.gov.uk').first()
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['data']['email_address'] == user.email_address
            assert json_resp['data']['id'] == str(user.id)


def test_post_user_missing_attribute_email(notify_api, notify_db, notify_db_session):
    """
    Tests POST endpoint '/' missing attribute email.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            assert User.query.count() == 0
            data = {
                "name": "Test User",
                "password": "password",
                "mobile_number": "+447700900986",
                "logged_in_at": None,
                "state": "active",
                "failed_login_count": 0,
                "permissions": {}
            }
            auth_header = create_authorization_header()
            headers = [('Content-Type', 'application/json'), auth_header]
            resp = client.post(
                url_for('user.create_user'),
                data=json.dumps(data),
                headers=headers)
            assert resp.status_code == 400
            assert User.query.count() == 0
            json_resp = json.loads(resp.get_data(as_text=True))
            assert {'email_address': ['Missing data for required field.']} == json_resp['message']


def test_post_user_missing_attribute_password(notify_api, notify_db, notify_db_session):
    """
    Tests POST endpoint '/' missing attribute password.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            assert User.query.count() == 0
            data = {
                "name": "Test User",
                "email_address": "user@digital.cabinet-office.gov.uk",
                "mobile_number": "+447700900986",
                "logged_in_at": None,
                "state": "active",
                "failed_login_count": 0,
                "permissions": {}
            }
            auth_header = create_authorization_header()
            headers = [('Content-Type', 'application/json'), auth_header]
            resp = client.post(
                url_for('user.create_user'),
                data=json.dumps(data),
                headers=headers)
            assert resp.status_code == 400
            assert User.query.count() == 0
            json_resp = json.loads(resp.get_data(as_text=True))
            assert {'password': ['Missing data for required field.']} == json_resp['message']


def test_put_user(notify_api, notify_db, notify_db_session, sample_service):
    """
    Tests PUT endpoint '/' to update a user.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            assert User.query.count() == 1
            sample_user = sample_service.users[0]
            new_email = 'new@digital.cabinet-office.gov.uk'
            data = {
                'name': sample_user.name,
                'email_address': new_email,
                'mobile_number': sample_user.mobile_number
            }
            auth_header = create_authorization_header()
            headers = [('Content-Type', 'application/json'), auth_header]
            resp = client.put(
                url_for('user.update_user', user_id=sample_user.id),
                data=json.dumps(data),
                headers=headers)
            assert resp.status_code == 200
            assert User.query.count() == 1
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['data']['email_address'] == new_email
            expected_permissions = default_service_permissions
            fetched = json_resp['data']

            assert str(sample_user.id) == fetched['id']
            assert sample_user.name == fetched['name']
            assert sample_user.mobile_number == fetched['mobile_number']
            assert new_email == fetched['email_address']
            assert sample_user.state == fetched['state']
            assert sorted(expected_permissions) == sorted(fetched['permissions'][str(sample_service.id)])


def test_put_user_update_password(notify_api,
                                  notify_db,
                                  notify_db_session,
                                  sample_service):
    """
    Tests PUT endpoint '/' to update a user including their password.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            assert User.query.count() == 1
            sample_user = sample_service.users[0]
            new_password = '1234567890'
            data = {
                'name': sample_user.name,
                'email_address': sample_user.email_address,
                'mobile_number': sample_user.mobile_number,
                'password': new_password
            }
            auth_header = create_authorization_header()
            headers = [('Content-Type', 'application/json'), auth_header]
            resp = client.put(
                url_for('user.update_user', user_id=sample_user.id),
                data=json.dumps(data),
                headers=headers)
            assert resp.status_code == 200
            assert User.query.count() == 1
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['data']['password_changed_at'] is not None
            data = {'password': new_password}
            auth_header = create_authorization_header()
            headers = [('Content-Type', 'application/json'), auth_header]
            resp = client.post(
                url_for('user.verify_user_password', user_id=str(sample_user.id)),
                data=json.dumps(data),
                headers=headers)
            assert resp.status_code == 204


def test_put_user_not_exists(notify_api, notify_db, notify_db_session, sample_user, fake_uuid):
    """
    Tests PUT endpoint '/' to update a user doesn't exist.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            assert User.query.count() == 1
            new_email = 'new@digital.cabinet-office.gov.uk'
            data = {'email_address': new_email}
            auth_header = create_authorization_header()
            headers = [('Content-Type', 'application/json'), auth_header]
            resp = client.put(
                url_for('user.update_user', user_id=fake_uuid),
                data=json.dumps(data),
                headers=headers)
            assert resp.status_code == 404
            assert User.query.count() == 1
            user = User.query.filter_by(id=str(sample_user.id)).first()
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['result'] == "error"
            assert json_resp['message'] == 'No result found'

            assert user == sample_user
            assert user.email_address != new_email


def test_get_user_by_email(notify_api, notify_db, notify_db_session, sample_service):

    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            sample_user = sample_service.users[0]
            header = create_authorization_header()
            url = url_for('user.get_by_email', email=sample_user.email_address)
            resp = client.get(url, headers=[header])
            assert resp.status_code == 200

            json_resp = json.loads(resp.get_data(as_text=True))
            expected_permissions = default_service_permissions
            fetched = json_resp['data']

            assert str(sample_user.id) == fetched['id']
            assert sample_user.name == fetched['name']
            assert sample_user.mobile_number == fetched['mobile_number']
            assert sample_user.email_address == fetched['email_address']
            assert sample_user.state == fetched['state']
            assert sorted(expected_permissions) == sorted(fetched['permissions'][str(sample_service.id)])


def test_get_user_by_email_not_found_returns_404(notify_api,
                                                 notify_db,
                                                 notify_db_session,
                                                 sample_user):

    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            header = create_authorization_header()
            url = url_for('user.get_by_email', email='no_user@digital.gov.uk')
            resp = client.get(url, headers=[header])
            assert resp.status_code == 404
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == 'No result found'


def test_get_user_by_email_bad_url_returns_404(notify_api,
                                               notify_db,
                                               notify_db_session,
                                               sample_user):

    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            header = create_authorization_header()
            url = '/user/email'
            resp = client.get(url, headers=[header])
            assert resp.status_code == 400
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == 'Invalid request. Email query string param required'


def test_get_user_with_permissions(notify_api,
                                   notify_db,
                                   notify_db_session,
                                   sample_service_permission):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            header = create_authorization_header()
            response = client.get(url_for('user.get_user', user_id=str(sample_service_permission.user.id)),
                                  headers=[header])
            assert response.status_code == 200
            permissions = json.loads(response.get_data(as_text=True))['data']['permissions']
            assert sample_service_permission.permission in permissions[str(sample_service_permission.service.id)]


def test_set_user_permissions(notify_api,
                              notify_db,
                              notify_db_session,
                              sample_user,
                              sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = json.dumps([{'permission': MANAGE_SETTINGS}])
            header = create_authorization_header()
            headers = [('Content-Type', 'application/json'), header]
            response = client.post(
                url_for(
                    'user.set_permissions',
                    user_id=str(sample_user.id),
                    service_id=str(sample_service.id)),
                headers=headers,
                data=data)

            assert response.status_code == 204
            permission = Permission.query.filter_by(permission=MANAGE_SETTINGS).first()
            assert permission.user == sample_user
            assert permission.service == sample_service
            assert permission.permission == MANAGE_SETTINGS


def test_set_user_permissions_multiple(notify_api,
                                       notify_db,
                                       notify_db_session,
                                       sample_user,
                                       sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = json.dumps([{'permission': MANAGE_SETTINGS}, {'permission': MANAGE_TEMPLATES}])
            header = create_authorization_header()
            headers = [('Content-Type', 'application/json'), header]
            response = client.post(
                url_for(
                    'user.set_permissions',
                    user_id=str(sample_user.id),
                    service_id=str(sample_service.id)),
                headers=headers,
                data=data)

            assert response.status_code == 204
            permission = Permission.query.filter_by(permission=MANAGE_SETTINGS).first()
            assert permission.user == sample_user
            assert permission.service == sample_service
            assert permission.permission == MANAGE_SETTINGS
            permission = Permission.query.filter_by(permission=MANAGE_TEMPLATES).first()
            assert permission.user == sample_user
            assert permission.service == sample_service
            assert permission.permission == MANAGE_TEMPLATES


def test_set_user_permissions_remove_old(notify_api,
                                         notify_db,
                                         notify_db_session,
                                         sample_user,
                                         sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = json.dumps([{'permission': MANAGE_SETTINGS}])
            header = create_authorization_header()
            headers = [('Content-Type', 'application/json'), header]
            response = client.post(
                url_for(
                    'user.set_permissions',
                    user_id=str(sample_user.id),
                    service_id=str(sample_service.id)),
                headers=headers,
                data=data)

            assert response.status_code == 204
            query = Permission.query.filter_by(user=sample_user)
            assert query.count() == 1
            assert query.first().permission == MANAGE_SETTINGS


@freeze_time("2016-01-01 11:09:00.061258")
def test_send_user_reset_password_should_send_reset_password_link(notify_api,
                                                                  sample_user,
                                                                  mocker,
                                                                  password_reset_email_template):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('notifications_utils.url_safe_token.generate_token', return_value='the-token')
            mocker.patch('uuid.uuid4', return_value='some_uuid')  # for the notification id
            mocker.patch('app.celery.tasks.send_email.apply_async')
            data = json.dumps({'email': sample_user.email_address})
            auth_header = create_authorization_header()
            resp = client.post(
                url_for('user.send_user_reset_password'),
                data=data,
                headers=[('Content-Type', 'application/json'), auth_header])

            message = {
                'template': str(password_reset_email_template.id),
                'template_version': password_reset_email_template.version,
                'to': sample_user.email_address,
                'personalisation': {
                    'user_name': sample_user.name,
                    'url': current_app.config['ADMIN_BASE_URL'] + '/new-password/' + 'the-token'
                }
            }
            assert resp.status_code == 204
            app.celery.tasks.send_email.apply_async.assert_called_once_with(
                [str(current_app.config['NOTIFY_SERVICE_ID']),
                 'some_uuid',
                 app.encryption.encrypt(message),
                 "2016-01-01T11:09:00.061258"],
                queue="notify")


def test_send_user_reset_password_should_return_400_when_email_is_missing(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = json.dumps({})
            auth_header = create_authorization_header()

            resp = client.post(
                url_for('user.send_user_reset_password'),
                data=data,
                headers=[('Content-Type', 'application/json'), auth_header])

        assert resp.status_code == 400
        assert json.loads(resp.get_data(as_text=True))['message'] == {'email': ['Missing data for required field.']}


def test_send_user_reset_password_should_return_400_when_user_doesnot_exist(notify_api,
                                                                            mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            bad_email_address = 'bad@email.gov.uk'
            data = json.dumps({'email': bad_email_address})
            auth_header = create_authorization_header()

        resp = client.post(
            url_for('user.send_user_reset_password'),
            data=data,
            headers=[('Content-Type', 'application/json'), auth_header])

        assert resp.status_code == 404
        assert json.loads(resp.get_data(as_text=True))['message'] == 'No result found'


def test_send_user_reset_password_should_return_400_when_data_is_not_email_address(notify_api, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            bad_email_address = 'bad.email.gov.uk'
            data = json.dumps({'email': bad_email_address})
            auth_header = create_authorization_header()

        resp = client.post(
            url_for('user.send_user_reset_password'),
            data=data,
            headers=[('Content-Type', 'application/json'), auth_header])

        assert resp.status_code == 400
        assert json.loads(resp.get_data(as_text=True))['message'] == {'email': ['Not a valid email address']}


@freeze_time("2016-01-01 11:09:00.061258")
def test_send_already_registered_email(notify_api, sample_user, already_registered_template, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = json.dumps({'email': sample_user.email_address})
            auth_header = create_authorization_header()
            mocker.patch('app.celery.tasks.send_email.apply_async')
            mocker.patch('uuid.uuid4', return_value='some_uuid')  # for the notification id

            resp = client.post(
                url_for('user.send_already_registered_email', user_id=str(sample_user.id)),
                data=data,
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 204
            message = {
                'template': str(already_registered_template.id),
                'template_version': already_registered_template.version,
                'to': sample_user.email_address,
                'personalisation': {
                    'signin_url': current_app.config['ADMIN_BASE_URL'] + '/sign-in',
                    'forgot_password_url': current_app.config['ADMIN_BASE_URL'] + '/forgot-password',
                    'feedback_url': current_app.config['ADMIN_BASE_URL'] + '/feedback'
                }
            }
            app.celery.tasks.send_email.apply_async.assert_called_once_with(
                (str(current_app.config['NOTIFY_SERVICE_ID']),
                 'some_uuid',
                 app.encryption.encrypt(message),
                 "2016-01-01T11:09:00.061258"),
                queue="notify")


def test_send_already_registered_email_returns_400_when_data_is_missing(notify_api, sample_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = json.dumps({})
            auth_header = create_authorization_header()

            resp = client.post(
                url_for('user.send_already_registered_email', user_id=str(sample_user.id)),
                data=data,
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 400
            assert json.loads(resp.get_data(as_text=True))['message'] == {'email': ['Missing data for required field.']}


@freeze_time("2016-01-01T11:09:00.061258")
def test_send_user_confirm_new_email_returns_204(notify_api, sample_user, change_email_confirmation_template, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocked = mocker.patch('app.celery.tasks.send_email.apply_async')
            mocker.patch('uuid.uuid4', return_value='some_uuid')  # for the notification id
            new_email = 'new_address@dig.gov.uk'
            data = json.dumps({'email': new_email})
            auth_header = create_authorization_header()

            resp = client.post(url_for('user.send_user_confirm_new_email', user_id=str(sample_user.id)),
                               data=data,
                               headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 204
            token_data = json.dumps({'user_id': str(sample_user.id), 'email': new_email})
            url = url_with_token(data=token_data, url='/user-profile/email/confirm/', config=current_app.config)
            message = {
                'template': current_app.config['CHANGE_EMAIL_CONFIRMATION_TEMPLATE_ID'],
                'template_version': 1,
                'to': 'new_address@dig.gov.uk',
                'personalisation': {
                    'name': sample_user.name,
                    'url': url,
                    'feedback_url': current_app.config['ADMIN_BASE_URL'] + '/feedback'
                }
            }
            mocked.assert_called_once_with((
                str(current_app.config['NOTIFY_SERVICE_ID']),
                "some_uuid",
                app.encryption.encrypt(message),
                "2016-01-01T11:09:00.061258"), queue="notify")


def test_send_user_confirm_new_email_returns_400_when_email_missing(notify_api, sample_user, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocked = mocker.patch('app.celery.tasks.send_email.apply_async')
            data = json.dumps({})
            auth_header = create_authorization_header()
            resp = client.post(url_for('user.send_user_confirm_new_email', user_id=str(sample_user.id)),
                               data=data,
                               headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 400
            assert json.loads(resp.get_data(as_text=True))['message'] == {'email': ['Missing data for required field.']}
            mocked.assert_not_called()
