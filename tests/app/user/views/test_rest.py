import json
from app.models import User
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


def test_put_user(notify_api, notify_db, notify_db_session, sample_user):
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
