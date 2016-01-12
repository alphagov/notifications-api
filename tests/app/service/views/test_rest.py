import json
from app.models import (Service, User)
from app.dao.services_dao import save_model_service
from tests.app.conftest import sample_user as create_sample_user
from flask import url_for


def test_get_service_list(notify_api, notify_db, notify_db_session, sample_service):
    """
    Tests GET endpoint '/' to retrieve entire service list.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            response = client.get(url_for('service.get_service'))
            assert response.status_code == 200
            json_resp = json.loads(response.get_data(as_text=True))
            # TODO assert correct json returned
            assert len(json_resp) == 1
            assert json_resp['data'][0]['name'] == sample_service.name
            assert json_resp['data'][0]['id'] == sample_service.id


def test_get_service(notify_api, notify_db, notify_db_session, sample_service):
    """
    Tests GET endpoint '/<service_id>' to retrieve a single service.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            resp = client.get(url_for('service.get_service',
                                      service_id=sample_service.id))
            assert resp.status_code == 200
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['data']['name'] == sample_service.name
            assert json_resp['data']['id'] == sample_service.id


def test_post_service(notify_api, notify_db, notify_db_session, sample_user):
    """
    Tests POST endpoint '/' to create a service.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            assert Service.query.count() == 0
            data = {
                'name': 'created service',
                'users': [sample_user.id],
                'limit': 1000,
                'restricted': False,
                'active': False}
            headers = [('Content-Type', 'application/json')]
            resp = client.post(
                url_for('service.create_service'),
                data=json.dumps(data),
                headers=headers)
            assert resp.status_code == 201
            service = Service.query.first()
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['data']['name'] == service.name
            assert json_resp['data']['limit'] == service.limit


def test_post_service_multiple_users(notify_api, notify_db, notify_db_session, sample_user):
    """
    Tests POST endpoint '/' to create a service with multiple users.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            another_user = create_sample_user(
                notify_db,
                notify_db_session,
                "new@digital.cabinet-office.gov.uk")
            assert Service.query.count() == 0
            data = {
                'name': 'created service',
                'users': [sample_user.id, another_user.id],
                'limit': 1000,
                'restricted': False,
                'active': False}
            headers = [('Content-Type', 'application/json')]
            resp = client.post(
                url_for('service.create_service'),
                data=json.dumps(data),
                headers=headers)
            assert resp.status_code == 201
            service = Service.query.first()
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['data']['name'] == service.name
            assert json_resp['data']['limit'] == service.limit
            assert len(service.users) == 2


def test_post_service_without_users_attribute(notify_api, notify_db, notify_db_session):
    """
    Tests POST endpoint '/' to create a service without 'users' attribute.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            assert Service.query.count() == 0
            data = {
                'name': 'created service',
                'limit': 1000,
                'restricted': False,
                'active': False}
            headers = [('Content-Type', 'application/json')]
            resp = client.post(
                url_for('service.create_service'),
                data=json.dumps(data),
                headers=headers)
            assert resp.status_code == 400
            assert Service.query.count() == 0
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['message'] == '{"users": ["Missing data for required attribute"]}'


def test_put_service(notify_api, notify_db, notify_db_session, sample_service):
    """
    Tests PUT endpoint '/<service_id>' to edit a service.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            assert Service.query.count() == 1
            sample_user = User.query.first()
            old_service = Service.query.first()
            new_name = 'updated service'
            data = {
                'name': new_name,
                'users': [sample_user.id],
                'limit': 1000,
                'restricted': False,
                'active': False}
            headers = [('Content-Type', 'application/json')]
            resp = client.put(
                url_for('service.update_service', service_id=old_service.id),
                data=json.dumps(data),
                headers=headers)
            assert Service.query.count() == 1
            assert resp.status_code == 200
            updated_service = Service.query.first()
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['data']['name'] == updated_service.name
            assert json_resp['data']['limit'] == updated_service.limit
            assert updated_service.name == new_name


def test_put_service_add_user(notify_api, notify_db, notify_db_session, sample_service):
    """
    Tests PUT endpoint '/<service_id>' add user to the service.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            assert Service.query.count() == 1
            another_user = create_sample_user(
                notify_db,
                notify_db_session,
                "new@digital.cabinet-office.gov.uk")
            sample_user = User.query.first()
            old_service = Service.query.first()
            new_name = 'updated service'
            data = {
                'name': new_name,
                'users': [sample_user.id, another_user.id],
                'limit': 1000,
                'restricted': False,
                'active': False}
            headers = [('Content-Type', 'application/json')]
            resp = client.put(
                url_for('service.update_service', service_id=old_service.id),
                data=json.dumps(data),
                headers=headers)
            assert Service.query.count() == 1
            assert resp.status_code == 200
            updated_service = Service.query.first()
            json_resp = json.loads(resp.get_data(as_text=True))
            assert len(json_resp['data']['users']) == 2
            assert sample_user.id in json_resp['data']['users']
            assert another_user.id in json_resp['data']['users']


def test_put_service_remove_user(notify_api, notify_db, notify_db_session, sample_service):
    """
    Tests PUT endpoint '/<service_id>' add user to the service.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            sample_user = User.query.first()
            another_user = create_sample_user(
                notify_db,
                notify_db_session,
                "new@digital.cabinet-office.gov.uk")
            data = {
                'name': sample_service.name,
                'users': [sample_user.id, another_user.id],
                'limit': sample_service.limit,
                'restricted': sample_service.restricted,
                'active': sample_service.active}
            save_model_service(sample_service, update_dict=data)
            assert Service.query.count() == 1
            sample_user = User.query.first()
            data['users'] = [another_user.id]
            headers = [('Content-Type', 'application/json')]
            resp = client.put(
                url_for('service.update_service', service_id=sample_service.id),
                data=json.dumps(data),
                headers=headers)
            assert Service.query.count() == 1
            assert resp.status_code == 200
            updated_service = Service.query.first()
            json_resp = json.loads(resp.get_data(as_text=True))
            assert len(json_resp['data']['users']) == 1
            assert sample_user.id not in json_resp['data']['users']
            assert another_user.id in json_resp['data']['users']


def test_delete_user(notify_api, notify_db, notify_db_session, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            service = Service.query.first()
            resp = client.delete(
                url_for('service.update_service', service_id=service.id),
                headers=[('Content-Type', 'application/json')])
            assert resp.status_code == 202
            json_resp = json.loads(resp.get_data(as_text=True))
            assert Service.query.count() == 0
