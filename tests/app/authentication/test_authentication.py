from datetime import datetime

import pytest
from flask import json, current_app
from freezegun import freeze_time
from notifications_python_client.authentication import create_jwt_token

from app import api_user
from app.dao.api_key_dao import get_unsigned_secrets, save_model_api_key, get_unsigned_secret, expire_api_key
from app.models import ApiKey, KEY_TYPE_NORMAL


def test_should_not_allow_request_with_no_token(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            response = client.get('/service')
            assert response.status_code == 401
            data = json.loads(response.get_data())
            assert data['message'] == {"token": ['Unauthorized, authentication token must be provided']}


def test_should_not_allow_request_with_incorrect_header(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            response = client.get(
                '/service',
                headers={'Authorization': 'Basic 1234'})
            assert response.status_code == 401
            data = json.loads(response.get_data())
            assert data['message'] == {"token": ['Unauthorized, authentication bearer scheme must be used']}


def test_should_not_allow_request_with_incorrect_token(notify_api, sample_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            response = client.get(
                '/service',
                headers={'Authorization': 'Bearer 1234'})
            assert response.status_code == 403
            data = json.loads(response.get_data())
            assert data['message'] == {"token": ['Invalid token: signature']}


def test_should_not_allow_invalid_secret(notify_api, sample_api_key):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            token = create_jwt_token(
                secret="not-so-secret",
                client_id=str(sample_api_key.service_id))
            response = client.get(
                '/service',
                headers={'Authorization': "Bearer {}".format(token)}
            )
            assert response.status_code == 403
            data = json.loads(response.get_data())
            assert data['message'] == {"token": ['Invalid token: signature']}


def test_should_allow_valid_token(notify_api, sample_api_key):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            token = __create_get_token(sample_api_key.service_id)
            response = client.get(
                '/service/{}'.format(str(sample_api_key.service_id)),
                headers={'Authorization': 'Bearer {}'.format(token)}
            )
            assert response.status_code == 200


def test_should_allow_valid_token_for_request_with_path_params(notify_api, sample_api_key):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            token = __create_get_token(sample_api_key.service_id)
            response = client.get(
                '/service/{}'.format(str(sample_api_key.service_id)),
                headers={'Authorization': 'Bearer {}'.format(token)})
            assert response.status_code == 200


def test_should_allow_valid_token_when_service_has_multiple_keys(notify_api, sample_api_key):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {'service': sample_api_key.service,
                    'name': 'some key name',
                    'created_by': sample_api_key.created_by,
                    'key_type': KEY_TYPE_NORMAL
                    }
            api_key = ApiKey(**data)
            save_model_api_key(api_key)
            token = __create_get_token(sample_api_key.service_id)
            response = client.get(
                '/service/{}'.format(str(sample_api_key.service_id)),
                headers={'Authorization': 'Bearer {}'.format(token)})
            assert response.status_code == 200


def test_authentication_passes_admin_client_token(notify_api,
                                                  notify_db,
                                                  notify_db_session,
                                                  sample_api_key):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            token = create_jwt_token(
                secret=current_app.config.get('ADMIN_CLIENT_SECRET'),
                client_id=current_app.config.get('ADMIN_CLIENT_USER_NAME'))
            response = client.get(
                '/service',
                headers={'Authorization': 'Bearer {}'.format(token)})
            assert response.status_code == 200


def test_authentication_passes_when_service_has_multiple_keys_some_expired(
        notify_api,
        notify_db,
        notify_db_session,
        sample_api_key):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            expired_key_data = {'service': sample_api_key.service,
                                'name': 'expired_key',
                                'expiry_date': datetime.utcnow(),
                                'created_by': sample_api_key.created_by,
                                'key_type': KEY_TYPE_NORMAL
                                }
            expired_key = ApiKey(**expired_key_data)
            save_model_api_key(expired_key)
            another_key = {'service': sample_api_key.service,
                           'name': 'another_key',
                           'created_by': sample_api_key.created_by,
                           'key_type': KEY_TYPE_NORMAL
                           }
            api_key = ApiKey(**another_key)
            save_model_api_key(api_key)
            token = create_jwt_token(
                secret=get_unsigned_secret(api_key.id),
                client_id=str(sample_api_key.service_id))
            response = client.get(
                '/service',
                headers={'Authorization': 'Bearer {}'.format(token)})
            assert response.status_code == 200


def test_authentication_returns_token_expired_when_service_uses_expired_key_and_has_multiple_keys(notify_api,
                                                                                                  notify_db,
                                                                                                  notify_db_session,
                                                                                                  sample_api_key):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            expired_key = {'service': sample_api_key.service,
                           'name': 'expired_key',
                           'created_by': sample_api_key.created_by,
                           'key_type': KEY_TYPE_NORMAL
                           }
            expired_api_key = ApiKey(**expired_key)
            save_model_api_key(expired_api_key)
            another_key = {'service': sample_api_key.service,
                           'name': 'another_key',
                           'created_by': sample_api_key.created_by,
                           'key_type': KEY_TYPE_NORMAL
                           }
            api_key = ApiKey(**another_key)
            save_model_api_key(api_key)
            token = create_jwt_token(
                secret=get_unsigned_secret(expired_api_key.id),
                client_id=str(sample_api_key.service_id))
            expire_api_key(service_id=sample_api_key.service_id, api_key_id=expired_api_key.id)
            response = client.get(
                '/service',
                headers={'Authorization': 'Bearer {}'.format(token)})
            assert response.status_code == 403
            data = json.loads(response.get_data())
            assert data['message'] == {"token": ['Invalid token: revoked']}


def test_authentication_returns_error_when_admin_client_has_no_secrets(notify_api,
                                                                       notify_db,
                                                                       notify_db_session):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            api_secret = notify_api.config.get('ADMIN_CLIENT_SECRET')
            token = create_jwt_token(
                secret=api_secret,
                client_id=notify_api.config.get('ADMIN_CLIENT_USER_NAME')
            )
            notify_api.config['ADMIN_CLIENT_SECRET'] = ''
            response = client.get(
                '/service',
                headers={'Authorization': 'Bearer {}'.format(token)})
            assert response.status_code == 403
            error_message = json.loads(response.get_data())
            assert error_message['message'] == {"token": ['Invalid token: signature']}
            notify_api.config['ADMIN_CLIENT_SECRET'] = api_secret


def test_authentication_returns_error_when_service_doesnt_exit(
    notify_api,
    notify_db,
    notify_db_session,
    sample_service,
    fake_uuid
):
    with notify_api.test_request_context(), notify_api.test_client() as client:
        # get service ID and secret the wrong way around
        token = create_jwt_token(
            secret=str(sample_service.id),
            client_id=fake_uuid
        )
        response = client.get(
            '/service',
            headers={'Authorization': 'Bearer {}'.format(token)}
        )
        assert response.status_code == 403
        error_message = json.loads(response.get_data())
        assert error_message['message'] == {'token': ['Invalid token: service not found']}


def test_authentication_returns_error_when_service_has_no_secrets(notify_api,
                                                                  notify_db,
                                                                  notify_db_session,
                                                                  sample_service,
                                                                  fake_uuid):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            token = create_jwt_token(
                secret=fake_uuid,
                client_id=str(sample_service.id))

            response = client.get(
                '/service',
                headers={'Authorization': 'Bearer {}'.format(token)})
            assert response.status_code == 403
            error_message = json.loads(response.get_data())
            assert error_message['message'] == {'token': ['Invalid token: no api keys for service']}


def test_should_attach_the_current_api_key_to_current_app(notify_api, sample_service, sample_api_key):
    with notify_api.test_request_context() as context, notify_api.test_client() as client:
        with pytest.raises(AttributeError):
            print(api_user)

        token = __create_get_token(sample_api_key.service_id)
        response = client.get(
            '/service/{}'.format(str(sample_api_key.service_id)),
            headers={'Authorization': 'Bearer {}'.format(token)}
        )
        assert response.status_code == 200
        assert api_user == sample_api_key


def test_should_return_403_when_token_is_expired(notify_api,
                                                 notify_db,
                                                 notify_db_session,
                                                 sample_api_key):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            with freeze_time('2001-01-01T12:00:00'):
                token = __create_get_token(sample_api_key.service_id)
            with freeze_time('2001-01-01T12:00:40'):
                response = client.get(
                    '/service',
                    headers={'Authorization': 'Bearer {}'.format(token)})
            assert response.status_code == 403
            error_message = json.loads(response.get_data())
            assert error_message['message'] == {'token': ['Invalid token: expired']}


def __create_get_token(service_id):
    if service_id:
        return create_jwt_token(secret=get_unsigned_secrets(service_id)[0],
                                client_id=str(service_id))
    else:
        return create_jwt_token(secret=get_unsigned_secrets(service_id)[0],
                                client_id=service_id)


def __create_post_token(service_id, request_body):
    return create_jwt_token(
        secret=get_unsigned_secrets(service_id)[0],
        client_id=str(service_id)
    )
