import pytest
from flask import json, url_for
from client.authentication import create_jwt_token


def test_should_not_allow_request_with_no_token(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            response = client.get(url_for('status.show_status'))
            assert response.status_code == 401
            data = json.loads(response.get_data())
            assert data['error'] == 'Unauthorized, authentication token must be provided'


def test_should_not_allow_request_with_incorrect_header(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            response = client.get(url_for('status.show_status'),
                                  headers={'Authorization': 'Basic 1234'})
            assert response.status_code == 401
            data = json.loads(response.get_data())
            assert data['error'] == 'Unauthorized, authentication bearer scheme must be used'


def test_should_not_allow_request_with_incorrect_token(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            response = client.get(url_for('status.show_status'),
                                  headers={'Authorization': 'Bearer 1234'})
            assert response.status_code == 403
            data = json.loads(response.get_data())
            assert data['error'] == 'Invalid token: signature'


def test_should_not_allow_incorrect_path(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            token = create_jwt_token(request_method="GET", request_path="/bad", secret="secret", client_id="client_id")
            response = client.get(url_for('status.show_status'),
                                  headers={'Authorization': "Bearer {}".format(token)})
            assert response.status_code == 403
            data = json.loads(response.get_data())
            assert data['error'] == 'Invalid token: request'


def test_should_not_allow_incorrect_method(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            token = create_jwt_token(request_method="POST", request_path="/", secret="secret", client_id="client_id")
            response = client.get(url_for('status.show_status'),
                                  headers={'Authorization': "Bearer {}".format(token)})
            assert response.status_code == 403
            data = json.loads(response.get_data())
            assert data['error'] == 'Invalid token: request'


def test_should_not_allow_invalid_secret(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            token = create_jwt_token(request_method="POST", request_path="/", secret="not-so-secret",
                                     client_id="client_id")
            response = client.get(url_for('status.show_status'),
                                  headers={'Authorization': "Bearer {}".format(token)})
            assert response.status_code == 403
            data = json.loads(response.get_data())
            assert data['error'] == 'Invalid token: signature'


def test_should_allow_valid_token(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            token = create_jwt_token(request_method="GET",
                                     request_path=url_for('status.show_status'),
                                     secret="secret",
                                     client_id="client_id")
            response = client.get(url_for('status.show_status'),
                                  headers={'Authorization': 'Bearer {}'.format(token)})
            assert response.status_code == 200


def test_should_allow_valid_token_with_post_body(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            json_body = json.dumps({
                "key1": "value1",
                "key2": "value2",
                "key3": "value3"
            })
            token = create_jwt_token(
                request_method="POST",
                request_path=url_for('status.show_status'),
                secret="secret",
                client_id="client_id",
                request_body=json_body
            )
            response = client.post(url_for('status.show_status'),
                                   data=json_body,
                                   headers={'Authorization': 'Bearer {}'.format(token)})
            assert response.status_code == 200


def test_should_not_allow_valid_token_with_invalid_post_body(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            json_body = json.dumps({
                "key1": "value1",
                "key2": "value2",
                "key3": "value3"
            })
            token = create_jwt_token(
                request_method="POST",
                request_path=url_for('status.show_status'),
                secret="secret",
                client_id="client_id",
                request_body=json_body
            )
            response = client.post(url_for('status.show_status'),
                                   data="spurious",
                                   headers={'Authorization': 'Bearer {}'.format(token)})
            assert response.status_code == 403
            data = json.loads(response.get_data())
            assert data['error'] == 'Invalid token: payload'
