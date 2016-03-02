import json

from flask import url_for

from app.models import (User, Permission, MANAGE_SETTINGS, MANAGE_TEMPLATES)
from app.dao.permissions_dao import default_service_permissions
from app import db
from tests import create_authorization_header


def test_get_user_list(notify_api, notify_db, notify_db_session, sample_service):
    """
    Tests GET endpoint '/' to retrieve entire user list.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            header = create_authorization_header(path=url_for('user.get_user'),
                                                 method='GET')
            response = client.get(url_for('user.get_user'),
                                  headers=[header])
            assert response.status_code == 200
            json_resp = json.loads(response.get_data(as_text=True))
            assert len(json_resp['data']) == 1
            sample_user = sample_service.users[0]
            expected_permissions = default_service_permissions
            fetched = json_resp['data'][0]

            assert sample_user.id == fetched['id']
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
            header = create_authorization_header(path=url_for('user.get_user', user_id=sample_user.id),
                                                 method='GET')
            resp = client.get(url_for('user.get_user',
                                      user_id=sample_user.id),
                              headers=[header])
            assert resp.status_code == 200
            json_resp = json.loads(resp.get_data(as_text=True))

            expected_permissions = default_service_permissions
            fetched = json_resp['data']

            assert sample_user.id == fetched['id']
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
                "password_changed_at": None,
                "logged_in_at": None,
                "state": "active",
                "failed_login_count": 0,
                "permissions": {}
            }
            auth_header = create_authorization_header(path=url_for('user.create_user'),
                                                      method='POST',
                                                      request_body=json.dumps(data))
            headers = [('Content-Type', 'application/json'), auth_header]
            resp = client.post(
                url_for('user.create_user'),
                data=json.dumps(data),
                headers=headers)
            assert resp.status_code == 201
            user = User.query.filter_by(email_address='user@digital.cabinet-office.gov.uk').first()
            json_resp = json.loads(resp.get_data(as_text=True))
            json_resp['data'] == {"email_address": user.email_address, "id": user.id}
            assert json_resp['data']['email_address'] == user.email_address
            assert json_resp['data']['id'] == user.id


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
                "password_changed_at": None,
                "logged_in_at": None,
                "state": "active",
                "failed_login_count": 0,
                "permissions": {}
            }
            auth_header = create_authorization_header(path=url_for('user.create_user'),
                                                      method='POST',
                                                      request_body=json.dumps(data))
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
                "password_changed_at": None,
                "logged_in_at": None,
                "state": "active",
                "failed_login_count": 0,
                "permissions": {}
            }
            auth_header = create_authorization_header(path=url_for('user.create_user'),
                                                      method='POST',
                                                      request_body=json.dumps(data))
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
            auth_header = create_authorization_header(path=url_for('user.update_user', user_id=sample_user.id),
                                                      method='PUT',
                                                      request_body=json.dumps(data))
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

            assert sample_user.id == fetched['id']
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
            auth_header = create_authorization_header(path=url_for('user.update_user', user_id=sample_user.id),
                                                      method='PUT',
                                                      request_body=json.dumps(data))
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
            auth_header = create_authorization_header(path=url_for('user.verify_user_password', user_id=sample_user.id),
                                                      method='POST',
                                                      request_body=json.dumps(data))
            headers = [('Content-Type', 'application/json'), auth_header]
            resp = client.post(
                url_for('user.verify_user_password', user_id=sample_user.id),
                data=json.dumps(data),
                headers=headers)
            assert resp.status_code == 204


def test_put_user_not_exists(notify_api, notify_db, notify_db_session, sample_user):
    """
    Tests PUT endpoint '/' to update a user doesn't exist.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            assert User.query.count() == 1
            new_email = 'new@digital.cabinet-office.gov.uk'
            data = {'email_address': new_email}
            auth_header = create_authorization_header(path=url_for('user.update_user', user_id="9999"),
                                                      method='PUT',
                                                      request_body=json.dumps(data))
            headers = [('Content-Type', 'application/json'), auth_header]
            resp = client.put(
                url_for('user.update_user', user_id="9999"),
                data=json.dumps(data),
                headers=headers)
            assert resp.status_code == 404
            assert User.query.count() == 1
            user = User.query.filter_by(id=sample_user.id).first()
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['result'] == "error"
            assert json_resp['message'] == "User not found"

            assert user == sample_user
            assert user.email_address != new_email


def test_get_user_by_email(notify_api, notify_db, notify_db_session, sample_service):

    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            sample_user = sample_service.users[0]
            header = create_authorization_header(path=url_for('user.get_by_email'), method='GET')
            url = url_for('user.get_by_email', email=sample_user.email_address)
            resp = client.get(url, headers=[header])
            assert resp.status_code == 200

            json_resp = json.loads(resp.get_data(as_text=True))
            expected_permissions = default_service_permissions
            fetched = json_resp['data']

            assert sample_user.id == fetched['id']
            assert sample_user.name == fetched['name']
            assert sample_user.mobile_number == fetched['mobile_number']
            assert sample_user.email_address == fetched['email_address']
            assert sample_user.state == fetched['state']
            assert sorted(expected_permissions) == sorted(fetched['permissions'][str(sample_service.id)])


def test_get_user_by_email_not_found_returns_400(notify_api,
                                                 notify_db,
                                                 notify_db_session,
                                                 sample_user):

    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            header = create_authorization_header(path=url_for('user.get_by_email'), method='GET')
            url = url_for('user.get_by_email', email='no_user@digital.gov.uk')
            resp = client.get(url, headers=[header])
            assert resp.status_code == 404
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == 'not found'


def test_get_user_by_email_bad_url_returns_404(notify_api,
                                               notify_db,
                                               notify_db_session,
                                               sample_user):

    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            header = create_authorization_header(path=url_for('user.get_by_email'), method='GET')
            url = '/user/email'
            resp = client.get(url, headers=[header])
            assert resp.status_code == 400
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == 'invalid request'


def test_get_user_with_permissions(notify_api,
                                   notify_db,
                                   notify_db_session,
                                   sample_service_permission):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            header = create_authorization_header(
                path=url_for('user.get_user', user_id=sample_service_permission.user.id),
                method='GET')
            response = client.get(url_for('user.get_user', user_id=sample_service_permission.user.id),
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
            header = create_authorization_header(
                path=url_for(
                    'user.set_permissions',
                    user_id=sample_user.id,
                    service_id=str(sample_service.id)),
                method='POST',
                request_body=data)
            headers = [('Content-Type', 'application/json'), header]
            response = client.post(
                url_for(
                    'user.set_permissions',
                    user_id=sample_user.id,
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
            header = create_authorization_header(
                path=url_for(
                    'user.set_permissions',
                    user_id=sample_user.id,
                    service_id=str(sample_service.id)),
                method='POST',
                request_body=data)
            headers = [('Content-Type', 'application/json'), header]
            response = client.post(
                url_for(
                    'user.set_permissions',
                    user_id=sample_user.id,
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
            header = create_authorization_header(
                path=url_for(
                    'user.set_permissions',
                    user_id=sample_user.id,
                    service_id=str(sample_service.id)),
                method='POST',
                request_body=data)
            headers = [('Content-Type', 'application/json'), header]
            response = client.post(
                url_for(
                    'user.set_permissions',
                    user_id=sample_user.id,
                    service_id=str(sample_service.id)),
                headers=headers,
                data=data)

            assert response.status_code == 204
            query = Permission.query.filter_by(user=sample_user)
            assert query.count() == 1
            assert query.first().permission == MANAGE_SETTINGS
