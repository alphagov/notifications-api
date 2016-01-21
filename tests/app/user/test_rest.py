import json
from flask import url_for
from app.models import (User, Service)
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
                "mobile_number": "+44 7700 900986",
                "password_changed_at": None,
                "logged_in_at": None,
                "state": "active",
                "failed_login_count": 0
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
                "mobile_number": "+44 7700 900986",
                "password_changed_at": None,
                "logged_in_at": None,
                "state": "active",
                "failed_login_count": 0
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
                "mobile_number": "+44 7700 900986",
                "password_changed_at": None,
                "logged_in_at": None,
                "state": "active",
                "failed_login_count": 0
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
                "mobile_number": "+44 7700 900986",
                "password_changed_at": None,
                "logged_in_at": None,
                "state": "active",
                "failed_login_count": 0
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
                "mobile_number": "+44 7700 900986",
                "password_changed_at": None,
                "logged_in_at": None,
                "state": "active",
                "failed_login_count": 0
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
                'email_address': new_email
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
                "mobile_number": "+44 7700 900986",
                "password_changed_at": None,
                "id": user.id,
                "logged_in_at": None,
                "state": "active",
                "failed_login_count": 0
            }
            assert json_resp['data'] == expected
            assert json_resp['data']['email_address'] == new_email


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
                                                      path=url_for('user.update_user', user_id="123"),
                                                      method='PUT',
                                                      request_body=json.dumps(data))
            headers = [('Content-Type', 'application/json'), auth_header]
            resp = client.put(
                url_for('user.update_user', user_id="123"),
                data=json.dumps(data),
                headers=headers)
            assert resp.status_code == 404
            assert User.query.count() == 2
            user = User.query.filter_by(id=sample_user.id).first()
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp == {'result': 'error', 'message': 'User not found'}
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
            assert json_resp['data']['id'] == another_service.id


def test_get_user_service_user_not_exists(notify_api, notify_db, notify_db_session, sample_service,
                                          sample_admin_service_id):
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
            print('** service users{}'.format(sample_service.users[0].id))
            resp = client.get(
                url_for('user.get_service_by_user_id', user_id="123423", service_id=sample_service.id),
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 404
            json_resp = json.loads(resp.get_data(as_text=True))
            assert "User not found" in json_resp['message']


def test_get_user_service_service_not_exists(notify_api, notify_db, notify_db_session, sample_service,
                                             sample_admin_service_id):
    """
    Tests GET endpoint "/<user_id>/service/<service_id>" 404 is returned for invalid service.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            user = User.query.first()
            assert Service.query.count() == 2
            auth_header = create_authorization_header(service_id=sample_admin_service_id,
                                                      path=url_for('user.get_service_by_user_id', user_id=user.id,
                                                                   service_id="12323423"),
                                                      method='GET')
            resp = client.get(
                url_for('user.get_service_by_user_id', user_id=user.id, service_id="12323423"),
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 404
            json_resp = json.loads(resp.get_data(as_text=True))
            assert "Service not found" in json_resp['message']


def test_delete_user(notify_api, notify_db, notify_db_session, sample_user, sample_admin_service_id):
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
                "mobile_number": "+44 7700 900986",
                "password_changed_at": None,
                "id": sample_user.id,
                "logged_in_at": None,
                "state": "active",
                "failed_login_count": 0

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


def test_user_verify_password(notify_api,
                              notify_db,
                              notify_db_session,
                              sample_user,
                              sample_admin_service_id):
    """
    Tests POST endpoint '/<user_id>/verify/password'
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = json.dumps({'password': 'password'})
            auth_header = create_authorization_header(
                service_id=sample_admin_service_id,
                path=url_for('user.verify_user_password', user_id=sample_user.id),
                method='POST',
                request_body=data)
            resp = client.post(
                url_for('user.verify_user_password', user_id=sample_user.id),
                data=data,
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 204


def test_user_verify_password_invalid_password(notify_api,
                                               notify_db,
                                               notify_db_session,
                                               sample_user,
                                               sample_admin_service_id):
    """
    Tests POST endpoint '/<user_id>/verify/password' invalid endpoint.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = json.dumps({'password': 'bad password'})
            auth_header = create_authorization_header(
                service_id=sample_admin_service_id,
                path=url_for('user.verify_user_password', user_id=sample_user.id),
                method='POST',
                request_body=data)
            resp = client.post(
                url_for('user.verify_user_password', user_id=sample_user.id),
                data=data,
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 400
            json_resp = json.loads(resp.get_data(as_text=True))
            assert 'Incorrect password' in json_resp['message']['password']


def test_user_verify_password_missing_password(notify_api,
                                               notify_db,
                                               notify_db_session,
                                               sample_user,
                                               sample_admin_service_id):
    """
    Tests POST endpoint '/<user_id>/verify/password' missing password.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = json.dumps({'bingo': 'bongo'})
            auth_header = create_authorization_header(
                service_id=sample_admin_service_id,
                path=url_for('user.verify_user_password', user_id=sample_user.id),
                method='POST',
                request_body=data)
            resp = client.post(
                url_for('user.verify_user_password', user_id=sample_user.id),
                data=data,
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 400
            json_resp = json.loads(resp.get_data(as_text=True))
            assert 'Required field missing data' in json_resp['message']['password']
