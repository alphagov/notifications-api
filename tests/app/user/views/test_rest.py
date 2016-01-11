import json
from app.models import (User, Service)
from tests.app.conftest import sample_service as create_sample_service
from flask import url_for


def test_get_user_list(notify_api, notify_db, notify_db_session, sample_user):
    """
    Tests GET endpoint '/' to retrieve entire user list.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            response = client.get(url_for('user.get_user'))
            assert response.status_code == 200
            json_resp = json.loads(response.get_data(as_text=True))
            # TODO assert correct json returned
            assert len(json_resp['data']) == 1
            assert json_resp['data'][0]['email_address'] == sample_user.email_address
            assert json_resp['data'][0]['id'] == sample_user.id


def test_get_user(notify_api, notify_db, notify_db_session, sample_user):
    """
    Tests GET endpoint '/<user_id>' to retrieve a single service.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            resp = client.get(url_for('user.get_user',
                                      user_id=sample_user.id))
            assert resp.status_code == 200
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['data']['email_address'] == sample_user.email_address
            assert json_resp['data']['id'] == sample_user.id


def test_post_user(notify_api, notify_db, notify_db_session):
    """
    Tests POST endpoint '/' to create a user.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            assert User.query.count() == 0
            data = {
                'email_address': 'user@digital.cabinet-office.gov.uk'}
            headers = [('Content-Type', 'application/json')]
            resp = client.post(
                url_for('user.create_user'),
                data=json.dumps(data),
                headers=headers)
            assert resp.status_code == 201
            user = User.query.first()
            json_resp = json.loads(resp.get_data(as_text=True))
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
                'blah': 'blah.blah'}
            headers = [('Content-Type', 'application/json')]
            resp = client.post(
                url_for('user.create_user'),
                data=json.dumps(data),
                headers=headers)
            assert resp.status_code == 400
            assert User.query.count() == 0
            json_resp = json.loads(resp.get_data(as_text=True))
            assert {'email_address': ['Missing data for required field.']} == json_resp['message']


def test_put_user(notify_api, notify_db, notify_db_session, sample_user):
    """
    Tests PUT endpoint '/' to update a user.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            assert User.query.count() == 1
            new_email = 'new@digital.cabinet-office.gov.uk'
            data = {
                'email_address': new_email}
            headers = [('Content-Type', 'application/json')]
            resp = client.put(
                url_for('user.update_user', user_id=sample_user.id),
                data=json.dumps(data),
                headers=headers)
            assert resp.status_code == 200
            assert User.query.count() == 1
            user = User.query.first()
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['data']['email_address'] == new_email
            assert json_resp['data']['id'] == user.id


def test_put_user_missing_email(notify_api, notify_db, notify_db_session, sample_user):
    """
    Tests PUT endpoint '/' missing attribute email.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            assert User.query.count() == 1
            new_email = 'new@digital.cabinet-office.gov.uk'
            data = {
                'blah': new_email}
            headers = [('Content-Type', 'application/json')]
            resp = client.put(
                url_for('user.update_user', user_id=sample_user.id),
                data=json.dumps(data),
                headers=headers)
            assert resp.status_code == 400
            assert User.query.count() == 1
            user = User.query.first()
            json_resp = json.loads(resp.get_data(as_text=True))
            assert user.email_address == sample_user.email_address
            assert {'email_address': ['Missing data for required field.']} == json_resp['message']


def test_get_user_services(notify_api, notify_db, notify_db_session, sample_service):
    """
    Tests GET endpoint "/<user_id>/service/<service_id>" to retrieve services for a user.
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
            assert Service.query.count() == 2
            resp = client.get(
                url_for('user.get_service_by_user_id', user_id=user.id),
                headers=[('Content-Type', 'application/json')])
            assert resp.status_code == 200
            json_resp = json.loads(resp.get_data(as_text=True))
            assert len(json_resp['data']) == 2


def test_get_user_service(notify_api, notify_db, notify_db_session, sample_service):
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
            assert Service.query.count() == 2
            resp = client.get(
                url_for('user.get_service_by_user_id', user_id=user.id, service_id=another_service.id),
                headers=[('Content-Type', 'application/json')])
            assert resp.status_code == 200
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['data']['name'] == another_name
            assert json_resp['data']['id'] == another_service.id


def test_get_user_service_user_not_exists(notify_api, notify_db, notify_db_session, sample_service):
    """
    Tests GET endpoint "/<user_id>/service/<service_id>" 404 is returned for invalid user.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            user = User.query.first()
            assert Service.query.count() == 1
            resp = client.get(
                url_for('user.get_service_by_user_id', user_id="123", service_id=sample_service.id),
                headers=[('Content-Type', 'application/json')])
            assert resp.status_code == 404
            json_resp = json.loads(resp.get_data(as_text=True))
            assert "User not found" in json_resp['message']


def test_get_user_service_service_not_exists(notify_api, notify_db, notify_db_session, sample_service):
    """
    Tests GET endpoint "/<user_id>/service/<service_id>" 404 is returned for invalid service.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            user = User.query.first()
            assert Service.query.count() == 1
            resp = client.get(
                url_for('user.get_service_by_user_id', user_id=user.id, service_id="123"),
                headers=[('Content-Type', 'application/json')])
            assert resp.status_code == 404
            json_resp = json.loads(resp.get_data(as_text=True))
            assert "Service not found" in json_resp['message']
