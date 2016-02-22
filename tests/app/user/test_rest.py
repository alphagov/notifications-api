import json
from flask import url_for
from app.models import (User, Service)
from app.dao.users_dao import save_model_user
from tests import create_authorization_header
from tests.app.conftest import sample_service as create_sample_service


def test_get_user_list(notify_api, notify_db, notify_db_session, sample_user, sample_admin_service_id):
    """
    Tests GET endpoint '/' to retrieve entire user list.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            header = create_authorization_header(service_id=sample_admin_service_id,
                                                 path=url_for('user.get_user'),
                                                 method='GET')
            response = client.get(url_for('user.get_user'),
                                  headers=[header])
            assert response.status_code == 200
            json_resp = json.loads(response.get_data(as_text=True))
            assert len(json_resp['data']) == 2
            expected = {
                "name": "Test User",
                "email_address": sample_user.email_address,
                "id": sample_user.id,
                "mobile_number": "+447700900986",
                "password_changed_at": None,
                "logged_in_at": None,
                "state": "active",
                "failed_login_count": 0,
                "permissions": []
            }
            assert expected in json_resp['data']


def test_get_user(notify_api, notify_db, notify_db_session, sample_user, sample_admin_service_id):
    """
    Tests GET endpoint '/<user_id>' to retrieve a single service.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            header = create_authorization_header(service_id=sample_admin_service_id,
                                                 path=url_for('user.get_user', user_id=sample_user.id),
                                                 method='GET')
            resp = client.get(url_for('user.get_user',
                                      user_id=sample_user.id),
                              headers=[header])
            assert resp.status_code == 200
            json_resp = json.loads(resp.get_data(as_text=True))
            expected = {
                "name": "Test User",
                "email_address": sample_user.email_address,
                "id": sample_user.id,
                "mobile_number": "+447700900986",
                "password_changed_at": None,
                "logged_in_at": None,
                "state": "active",
                "failed_login_count": 0,
                "permissions": []
            }
            assert json_resp['data'] == expected


def test_post_user(notify_api, notify_db, notify_db_session, sample_admin_service_id):
    """
    Tests POST endpoint '/' to create a user.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            assert User.query.count() == 1
            data = {
                "name": "Test User",
                "email_address": "user@digital.cabinet-office.gov.uk",
                "password": "password",
                "mobile_number": "+447700900986",
                "password_changed_at": None,
                "logged_in_at": None,
                "state": "active",
                "failed_login_count": 0,
                "permissions": []
            }
            auth_header = create_authorization_header(service_id=sample_admin_service_id,
                                                      path=url_for('user.create_user'),
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


def test_post_user_missing_attribute_email(notify_api, notify_db, notify_db_session, sample_admin_service_id):
    """
    Tests POST endpoint '/' missing attribute email.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            assert User.query.count() == 1
            data = {
                "name": "Test User",
                "password": "password",
                "mobile_number": "+447700900986",
                "password_changed_at": None,
                "logged_in_at": None,
                "state": "active",
                "failed_login_count": 0,
                "permissions": []
            }
            auth_header = create_authorization_header(service_id=sample_admin_service_id,
                                                      path=url_for('user.create_user'),
                                                      method='POST',
                                                      request_body=json.dumps(data))
            headers = [('Content-Type', 'application/json'), auth_header]
            resp = client.post(
                url_for('user.create_user'),
                data=json.dumps(data),
                headers=headers)
            assert resp.status_code == 400
            assert User.query.count() == 1
            json_resp = json.loads(resp.get_data(as_text=True))
            assert {'email_address': ['Missing data for required field.']} == json_resp['message']


def test_post_user_missing_attribute_password(notify_api, notify_db, notify_db_session, sample_admin_service_id):
    """
    Tests POST endpoint '/' missing attribute password.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            assert User.query.count() == 1
            data = {
                "name": "Test User",
                "email_address": "user@digital.cabinet-office.gov.uk",
                "mobile_number": "+447700900986",
                "password_changed_at": None,
                "logged_in_at": None,
                "state": "active",
                "failed_login_count": 0,
                "permissions": []
            }
            auth_header = create_authorization_header(service_id=sample_admin_service_id,
                                                      path=url_for('user.create_user'),
                                                      method='POST',
                                                      request_body=json.dumps(data))
            headers = [('Content-Type', 'application/json'), auth_header]
            resp = client.post(
                url_for('user.create_user'),
                data=json.dumps(data),
                headers=headers)
            assert resp.status_code == 400
            assert User.query.count() == 1
            json_resp = json.loads(resp.get_data(as_text=True))
            assert {'password': ['Missing data for required field.']} == json_resp['message']


def test_put_user(notify_api, notify_db, notify_db_session, sample_user, sample_admin_service_id):
    """
    Tests PUT endpoint '/' to update a user.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            assert User.query.count() == 2
            new_email = 'new@digital.cabinet-office.gov.uk'
            data = {
                'name': sample_user.name,
                'email_address': new_email,
                'mobile_number': sample_user.mobile_number,
                'permissions': []
            }
            auth_header = create_authorization_header(service_id=sample_admin_service_id,
                                                      path=url_for('user.update_user', user_id=sample_user.id),
                                                      method='PUT',
                                                      request_body=json.dumps(data))
            headers = [('Content-Type', 'application/json'), auth_header]
            resp = client.put(
                url_for('user.update_user', user_id=sample_user.id),
                data=json.dumps(data),
                headers=headers)
            assert resp.status_code == 200
            assert User.query.count() == 2
            user = User.query.filter_by(email_address=new_email).first()
            json_resp = json.loads(resp.get_data(as_text=True))
            expected = {
                "name": "Test User",
                "email_address": new_email,
                "mobile_number": "+447700900986",
                "password_changed_at": None,
                "id": user.id,
                "logged_in_at": None,
                "state": "active",
                "failed_login_count": 0,
                "permissions": []
            }
            assert json_resp['data'] == expected
            assert json_resp['data']['email_address'] == new_email


def test_put_user_update_password(notify_api,
                                  notify_db,
                                  notify_db_session,
                                  sample_user,
                                  sample_admin_service_id):
    """
    Tests PUT endpoint '/' to update a user including their password.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            assert User.query.count() == 2
            new_password = '1234567890'
            data = {
                'name': sample_user.name,
                'email_address': sample_user.email_address,
                'mobile_number': sample_user.mobile_number,
                'password': new_password,
                'permissions': []
            }
            auth_header = create_authorization_header(service_id=sample_admin_service_id,
                                                      path=url_for('user.update_user', user_id=sample_user.id),
                                                      method='PUT',
                                                      request_body=json.dumps(data))
            headers = [('Content-Type', 'application/json'), auth_header]
            resp = client.put(
                url_for('user.update_user', user_id=sample_user.id),
                data=json.dumps(data),
                headers=headers)
            assert resp.status_code == 200
            assert User.query.count() == 2
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['data']['password_changed_at'] is not None
            data = {'password': new_password}
            auth_header = create_authorization_header(service_id=sample_admin_service_id,
                                                      path=url_for('user.verify_user_password', user_id=sample_user.id),
                                                      method='POST',
                                                      request_body=json.dumps(data))
            headers = [('Content-Type', 'application/json'), auth_header]
            resp = client.post(
                url_for('user.verify_user_password', user_id=sample_user.id),
                data=json.dumps(data),
                headers=headers)
            assert resp.status_code == 204


def test_put_user_not_exists(notify_api, notify_db, notify_db_session, sample_user, sample_admin_service_id):
    """
    Tests PUT endpoint '/' to update a user doesn't exist.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            assert User.query.count() == 2
            new_email = 'new@digital.cabinet-office.gov.uk'
            data = {'email_address': new_email}
            auth_header = create_authorization_header(service_id=sample_admin_service_id,
                                                      path=url_for('user.update_user', user_id="9999"),
                                                      method='PUT',
                                                      request_body=json.dumps(data))
            headers = [('Content-Type', 'application/json'), auth_header]
            resp = client.put(
                url_for('user.update_user', user_id="9999"),
                data=json.dumps(data),
                headers=headers)
            assert resp.status_code == 404
            assert User.query.count() == 2
            user = User.query.filter_by(id=sample_user.id).first()
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp == {'error': 'No result found'}
            assert user == sample_user
            assert user.email_address != new_email


def test_get_user_services(notify_api, notify_db, notify_db_session, sample_service, sample_admin_service_id):
    """
    Tests GET endpoint "/<user_id>/service/<service_id>" to retrieve services for a user.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            user = User.query.get(sample_service.users[0].id)
            another_name = "another name"
            create_sample_service(
                notify_db,
                notify_db_session,
                service_name=another_name,
                user=user)
            assert Service.query.count() == 3
            auth_header = create_authorization_header(service_id=sample_admin_service_id,
                                                      path=url_for('user.get_service_by_user_id', user_id=user.id),
                                                      method='GET')
            resp = client.get(
                url_for('user.get_service_by_user_id', user_id=user.id),
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 200
            json_resp = json.loads(resp.get_data(as_text=True))
            assert len(json_resp['data']) == 2


def test_get_user_service(notify_api, notify_db, notify_db_session, sample_service, sample_admin_service_id):
    """
    Tests GET endpoint "/<user_id>/service/<service_id>" to retrieve a service for a user.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            user = User.query.first()
            another_name = "another name"
            another_service = create_sample_service(
                notify_db,
                notify_db_session,
                service_name=another_name,
                user=user)
            assert Service.query.count() == 3
            auth_header = create_authorization_header(service_id=sample_admin_service_id,
                                                      path=url_for('user.get_service_by_user_id', user_id=user.id,
                                                                   service_id=another_service.id),
                                                      method='GET')
            resp = client.get(
                url_for('user.get_service_by_user_id', user_id=user.id, service_id=another_service.id),
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 200
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['data']['name'] == another_name
            assert json_resp['data']['id'] == str(another_service.id)


def test_get_user_service_user_not_exists(notify_api, sample_service, sample_admin_service_id):
    """
    Tests GET endpoint "/<user_id>/service/<service_id>" 404 is returned for invalid user.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            assert Service.query.count() == 2
            auth_header = create_authorization_header(service_id=sample_admin_service_id,
                                                      path=url_for('user.get_service_by_user_id', user_id="123423",
                                                                   service_id=sample_service.id),
                                                      method='GET')
            resp = client.get(
                url_for('user.get_service_by_user_id', user_id="123423", service_id=sample_service.id),
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 404
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp == {'error': 'No result found'}


def test_get_user_service_service_not_exists(notify_api, sample_service):
    """
    Tests GET endpoint "/<user_id>/service/<service_id>" 404 is returned for invalid service.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            user = User.query.first()
            assert Service.query.count() == 1
            import uuid
            missing_service_id = uuid.uuid4()
            auth_header = create_authorization_header(path=url_for('user.get_service_by_user_id', user_id=user.id,
                                                                   service_id=missing_service_id),
                                                      method='GET')
            resp = client.get(
                url_for('user.get_service_by_user_id', user_id=user.id, service_id=missing_service_id),
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 404
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp == {'error': 'No result found'}


def test_delete_user(notify_api, sample_user, sample_admin_service_id):
    """
    Tests DELETE endpoint '/<user_id>' delete user.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            assert User.query.count() == 2
            auth_header = create_authorization_header(service_id=sample_admin_service_id,
                                                      path=url_for('user.update_user', user_id=sample_user.id),
                                                      method='DELETE')
            resp = client.delete(
                url_for('user.update_user', user_id=sample_user.id),
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 202
            json_resp = json.loads(resp.get_data(as_text=True))
            assert User.query.count() == 1
            expected = {
                "name": "Test User",
                "email_address": sample_user.email_address,
                "mobile_number": "+447700900986",
                "password_changed_at": None,
                "id": sample_user.id,
                "logged_in_at": None,
                "state": "active",
                "failed_login_count": 0,
                "permissions": []

            }
            assert json_resp['data'] == expected


def test_delete_user_not_exists(notify_api, notify_db, notify_db_session, sample_user, sample_admin_service_id):
    """
    Tests DELETE endpoint '/<user_id>' delete user.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            assert User.query.count() == 2
            auth_header = create_authorization_header(service_id=sample_admin_service_id,
                                                      path=url_for('user.update_user', user_id='99999'),
                                                      method='DELETE')
            resp = client.delete(
                url_for('user.update_user', user_id="99999"),
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 404
            assert User.query.count() == 2
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp == {'error': 'No result found'}


def test_post_with_permissions(notify_api, notify_db, notify_db_session, sample_admin_service_id):
    """
    Tests POST endpoint '/' to create a user with permissions.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            assert User.query.count() == 1
            permissions = ['new permission']
            data = {
                "name": "Test User",
                "email_address": "user@digital.cabinet-office.gov.uk",
                "password": "password",
                "mobile_number": "+447700900986",
                "password_changed_at": None,
                "logged_in_at": None,
                "state": "active",
                "failed_login_count": 0,
                "permissions": permissions
            }
            auth_header = create_authorization_header(service_id=sample_admin_service_id,
                                                      path=url_for('user.create_user'),
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
            assert json_resp['data']['permissions'] == permissions


def test_put_add_permissions(notify_api, notify_db, notify_db_session, sample_user, sample_admin_service_id):
    """
    Tests PUT endpoint '/' to update user permissions.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            permissions = ['one permission', 'another permission']
            data = {
                'name': sample_user.name,
                'email_address': sample_user.email_address,
                'mobile_number': sample_user.mobile_number,
                'permissions': permissions
            }
            auth_header = create_authorization_header(service_id=sample_admin_service_id,
                                                      path=url_for('user.update_user', user_id=sample_user.id),
                                                      method='PUT',
                                                      request_body=json.dumps(data))
            headers = [('Content-Type', 'application/json'), auth_header]
            resp = client.put(
                url_for('user.update_user', user_id=sample_user.id),
                data=json.dumps(data),
                headers=headers)
            assert resp.status_code == 200
            assert User.query.count() == 2
            user = User.query.filter_by(email_address=sample_user.email_address).first()
            json_resp = json.loads(resp.get_data(as_text=True))
            expected = {
                "name": user.name,
                "email_address": user.email_address,
                "mobile_number": user.mobile_number,
                "password_changed_at": None,
                "id": user.id,
                "logged_in_at": None,
                "state": user.state,
                "failed_login_count": 0,
                "permissions": permissions
            }
            assert json_resp['data'] == expected


def test_put_remove_permissions(notify_api, notify_db, notify_db_session, sample_user, sample_admin_service_id):
    """
    Tests PUT endpoint '/' to update user permissions.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            old_permissions = ['one permission', 'another permission']
            save_model_user(sample_user, {'permissions': old_permissions})
            permissions = ['new permissions']
            data = {
                'name': sample_user.name,
                'email_address': sample_user.email_address,
                'mobile_number': sample_user.mobile_number,
                'permissions': permissions
            }
            auth_header = create_authorization_header(service_id=sample_admin_service_id,
                                                      path=url_for('user.update_user', user_id=sample_user.id),
                                                      method='PUT',
                                                      request_body=json.dumps(data))
            headers = [('Content-Type', 'application/json'), auth_header]
            resp = client.put(
                url_for('user.update_user', user_id=sample_user.id),
                data=json.dumps(data),
                headers=headers)
            assert resp.status_code == 200
            assert User.query.count() == 2
            user = User.query.filter_by(email_address=sample_user.email_address).first()
            json_resp = json.loads(resp.get_data(as_text=True))
            expected = {
                "name": user.name,
                "email_address": user.email_address,
                "mobile_number": user.mobile_number,
                "password_changed_at": None,
                "id": user.id,
                "logged_in_at": None,
                "state": user.state,
                "failed_login_count": 0,
                "permissions": permissions
            }
            assert json_resp['data'] == expected
