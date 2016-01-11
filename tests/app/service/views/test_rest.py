import json
from app.models import (Service, User)
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


def test_put_service(notify_api, notify_db, notify_db_session, sample_service):
    """
    Tests Put endpoint '/<service_id' to edit a service.
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
