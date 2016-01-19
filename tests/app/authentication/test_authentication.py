from client.authentication import create_jwt_token
from flask import json, url_for

from app.dao.api_key_dao import get_unsigned_secrets, save_model_api_key
from app.models import ApiKey


def test_should_not_allow_request_with_no_token(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            response = client.get(url_for('service.get_service'))
            assert response.status_code == 401
            data = json.loads(response.get_data())
            assert data['error'] == 'Unauthorized, authentication token must be provided'


def test_should_not_allow_request_with_incorrect_header(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            response = client.get(url_for('service.get_service'),
                                  headers={'Authorization': 'Basic 1234'})
            assert response.status_code == 401
            data = json.loads(response.get_data())
            assert data['error'] == 'Unauthorized, authentication bearer scheme must be used'


def test_should_not_allow_request_with_incorrect_token(notify_api, notify_db, notify_db_session, sample_api_key):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            response = client.get(url_for('service.get_service'),
                                  headers={'Authorization': 'Bearer 1234'})
            assert response.status_code == 403
            data = json.loads(response.get_data())
            assert data['error'] == 'Invalid token: signature'


def test_should_not_allow_incorrect_path(notify_api, notify_db, notify_db_session, sample_api_key):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            token = create_jwt_token(request_method="GET",
                                     request_path="/bad",
                                     secret=get_unsigned_secrets(sample_api_key.service_id)[0],
                                     client_id=sample_api_key.service_id)
            response = client.get(url_for('service.get_service'),
                                  headers={'Authorization': "Bearer {}".format(token)})
            assert response.status_code == 403
            data = json.loads(response.get_data())
            assert data['error'] == 'Invalid token: request'


def test_should_not_allow_incorrect_method(notify_api, notify_db, notify_db_session, sample_api_key):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            token = __create_post_token(sample_api_key.service_id, {})
            response = client.get(url_for('service.get_service'),
                                  headers={'Authorization': "Bearer {}".format(token)})
            assert response.status_code == 403
            data = json.loads(response.get_data())
            assert data['error'] == 'Invalid token: request'


def test_should_not_allow_invalid_secret(notify_api, notify_db, notify_db_session, sample_api_key):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            token = create_jwt_token(request_method="POST", request_path="/", secret="not-so-secret",
                                     client_id=sample_api_key.service_id)
            response = client.get(url_for('service.get_service'),
                                  headers={'Authorization': "Bearer {}".format(token)})
            assert response.status_code == 403
            data = json.loads(response.get_data())
            assert data['error'] == 'Invalid token: signature'


def test_should_allow_valid_token(notify_api, notify_db, notify_db_session, sample_api_key):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            token = __create_get_token(sample_api_key.service_id)
            response = client.get(url_for('service.get_service'),
                                  headers={'Authorization': 'Bearer {}'.format(token)})
            assert response.status_code == 200


def test_should_allow_valid_token_when_service_has_multiple_keys(notify_api, notify_db, notify_db_session,
                                                                 sample_api_key):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {'service_id': sample_api_key.service_id, 'name': 'some key name'}
            api_key = ApiKey(**data)
            save_model_api_key(api_key)
            token = __create_get_token(sample_api_key.service_id)
            response = client.get(url_for('service.get_service'),
                                  headers={'Authorization': 'Bearer {}'.format(token)})
            assert response.status_code == 200

JSON_BODY = json.dumps({
    'name': 'new name'
})


# def test_should_allow_valid_token_with_post_body(
#         notify_api, notify_db, notify_db_session, sample_api_key):
#     with notify_api.test_request_context():
#         with notify_api.test_client() as client:
#             token = create_jwt_token(
#                 request_method="PUT",
#                 request_path=url_for('service.update_service', service_id=sample_api_key.service_id),
#                 secret=get_unsigned_secret(sample_api_key.service_id),
#                 client_id=sample_api_key.service_id,
#                 request_body=JSON_BODY
#             )
#             response = client.put(
#                 url_for('service.update_service', service_id=sample_api_key.service_id),
#                 data=JSON_BODY,
#                 headers=[('Content-type', 'application-json'), ('Authorization', 'Bearer {}'.format(token))]
#             )
#             assert response.status_code == 200


def test_should_not_allow_valid_token_with_invalid_post_body(notify_api, notify_db, notify_db_session, sample_api_key):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            token = __create_post_token(sample_api_key.service_id, JSON_BODY)
            response = client.post(url_for('service.create_service'),
                                   data="spurious",
                                   headers={'Authorization': 'Bearer {}'.format(token)})
            assert response.status_code == 403
            data = json.loads(response.get_data())
            assert data['error'] == 'Invalid token: payload'


def __create_get_token(service_id):
    return create_jwt_token(request_method="GET",
                            request_path=url_for('service.get_service'),
                            secret=get_unsigned_secrets(service_id)[0],
                            client_id=service_id)


def __create_post_token(service_id, request_body):
    return create_jwt_token(
        request_method="POST",
        request_path=url_for('service.create_service'),
        secret=get_unsigned_secrets(service_id)[0],
        client_id=service_id,
        request_body=request_body
    )
