import time
import uuid
from datetime import datetime
from unittest.mock import call

import jwt
import pytest
from flask import current_app, json, request
from freezegun import freeze_time
from notifications_python_client.authentication import create_jwt_token

from app import api_user
from app.authentication.auth import (
    GENERAL_TOKEN_ERROR_MESSAGE,
    AuthError,
    requires_admin_auth,
    requires_auth,
)
from app.dao.api_key_dao import (
    expire_api_key,
    get_model_api_keys,
    get_unsigned_secret,
    get_unsigned_secrets,
    save_model_api_key,
)
from app.dao.services_dao import dao_fetch_service_by_id
from app.models import KEY_TYPE_NORMAL, ApiKey
from tests.conftest import set_config, set_config_values


@pytest.mark.parametrize('auth_fn', [requires_auth, requires_admin_auth])
def test_should_not_allow_request_with_no_token(client, auth_fn):
    request.headers = {}
    with pytest.raises(AuthError) as exc:
        auth_fn()
    assert exc.value.short_message == 'Unauthorized: authentication token must be provided'


@pytest.mark.parametrize('auth_fn', [requires_auth, requires_admin_auth])
def test_should_not_allow_request_with_incorrect_header(client, auth_fn):
    request.headers = {'Authorization': 'Basic 1234'}
    with pytest.raises(AuthError) as exc:
        auth_fn()
    assert exc.value.short_message == 'Unauthorized: authentication bearer scheme must be used'


@pytest.mark.parametrize('auth_fn', [requires_auth, requires_admin_auth])
def test_should_not_allow_request_with_incorrect_token(client, auth_fn):
    request.headers = {'Authorization': 'Bearer 1234'}
    with pytest.raises(AuthError) as exc:
        auth_fn()
    assert exc.value.short_message == GENERAL_TOKEN_ERROR_MESSAGE


@pytest.mark.parametrize('auth_fn', [requires_auth, requires_admin_auth])
def test_should_not_allow_request_with_no_iss(client, auth_fn):
    # code copied from notifications_python_client.authentication.py::create_jwt_token
    headers = {
        "typ": 'JWT',
        "alg": 'HS256'
    }

    claims = {
        # 'iss': not provided
        'iat': int(time.time())
    }

    token = jwt.encode(payload=claims, key=str(uuid.uuid4()), headers=headers)

    request.headers = {'Authorization': 'Bearer {}'.format(token)}
    with pytest.raises(AuthError) as exc:
        auth_fn()
    assert exc.value.short_message == 'Invalid token: iss field not provided'


def test_auth_should_not_allow_request_with_no_iat(client, sample_api_key):
    iss = str(sample_api_key.service_id)
    # code copied from notifications_python_client.authentication.py::create_jwt_token
    headers = {
        "typ": 'JWT',
        "alg": 'HS256'
    }

    claims = {
        'iss': iss
        # 'iat': not provided
    }

    token = jwt.encode(payload=claims, key=str(uuid.uuid4()), headers=headers)

    request.headers = {'Authorization': 'Bearer {}'.format(token)}
    with pytest.raises(AuthError) as exc:
        requires_auth()
    assert exc.value.short_message == 'Invalid token: API key not found'


def test_auth_should_not_allow_request_with_non_hs256_algorithm(client, sample_api_key):
    iss = str(sample_api_key.service_id)
    # code copied from notifications_python_client.authentication.py::create_jwt_token
    headers = {
        "typ": 'JWT',
        "alg": 'HS512'
    }

    claims = {
        'iss': iss,
        'iat': int(time.time())
    }

    token = jwt.encode(payload=claims, key=str(uuid.uuid4()), headers=headers)

    request.headers = {'Authorization': 'Bearer {}'.format(token)}
    with pytest.raises(AuthError) as exc:
        requires_auth()
    assert exc.value.short_message == 'Invalid token: algorithm used is not HS256'


def test_admin_auth_should_not_allow_request_with_no_iat(client):
    client_id = current_app.config['ADMIN_CLIENT_USER_NAME']
    secret = current_app.config['INTERNAL_CLIENT_API_KEYS'][client_id][0]

    # code copied from notifications_python_client.authentication.py::create_jwt_token
    headers = {
        "typ": 'JWT',
        "alg": 'HS256'
    }

    claims = {
        'iss': client_id,
        # 'iat': not provided
    }

    token = jwt.encode(payload=claims, key=secret, headers=headers)

    request.headers = {'Authorization': 'Bearer {}'.format(token)}
    with pytest.raises(AuthError) as exc:
        requires_admin_auth()
    assert exc.value.short_message == "Unauthorized: API authentication token not found"


def test_admin_auth_should_not_allow_request_with_old_iat(client):
    client_id = current_app.config['ADMIN_CLIENT_USER_NAME']
    secret = current_app.config['INTERNAL_CLIENT_API_KEYS'][client_id][0]

    # code copied from notifications_python_client.authentication.py::create_jwt_token
    headers = {
        "typ": 'JWT',
        "alg": 'HS256'
    }

    claims = {
        'iss': client_id,
        'iat': int(time.time()) - 60
    }

    token = jwt.encode(payload=claims, key=secret, headers=headers)

    request.headers = {'Authorization': 'Bearer {}'.format(token)}
    with pytest.raises(AuthError) as exc:
        requires_admin_auth()
    assert exc.value.short_message == "Invalid token: expired, check that your system clock is accurate"


def test_auth_should_not_allow_request_with_extra_claims(client, sample_api_key):
    iss = str(sample_api_key.service_id)
    key = get_unsigned_secrets(sample_api_key.service_id)[0]

    headers = {
        "typ": 'JWT',
        "alg": 'HS256'
    }

    claims = {
        'iss': iss,
        'iat': int(time.time()),
        'aud': 'notifications.service.gov.uk'  # extra claim that we don't support
    }

    token = jwt.encode(payload=claims, key=key, headers=headers)

    request.headers = {'Authorization': 'Bearer {}'.format(token)}
    with pytest.raises(AuthError) as exc:
        requires_auth()
    assert exc.value.short_message == GENERAL_TOKEN_ERROR_MESSAGE


def test_should_not_allow_invalid_secret(client, sample_api_key):
    token = create_jwt_token(
        secret="not-so-secret",
        client_id=str(sample_api_key.service_id))
    response = client.get(
        '/notifications',
        headers={'Authorization': "Bearer {}".format(token)}
    )
    assert response.status_code == 403
    data = json.loads(response.get_data())
    assert data['message'] == {"token": ['Invalid token: API key not found']}


@pytest.mark.parametrize('scheme', ['bearer', 'Bearer'])
def test_should_allow_valid_token(client, sample_api_key, scheme):
    token = __create_token(sample_api_key.service_id)
    response = client.get('/notifications', headers={'Authorization': '{} {}'.format(scheme, token)})
    assert response.status_code == 200


@pytest.mark.parametrize('service_id', ['not-a-valid-id', 1234])
def test_should_not_allow_service_id_that_is_not_the_wrong_data_type(client, sample_api_key, service_id):
    token = create_jwt_token(secret=get_unsigned_secrets(sample_api_key.service_id)[0],
                             client_id=service_id)
    response = client.get(
        '/notifications',
        headers={'Authorization': "Bearer {}".format(token)}
    )
    assert response.status_code == 403
    data = json.loads(response.get_data())
    assert data['message'] == {"token": ['Invalid token: service id is not the right data type']}


def test_should_allow_valid_token_for_request_with_path_params_for_public_url(client, sample_api_key):
    token = __create_token(sample_api_key.service_id)
    response = client.get('/notifications', headers={'Authorization': 'Bearer {}'.format(token)})
    assert response.status_code == 200


def test_should_allow_valid_token_for_request_with_path_params_for_admin_url(client):
    client_id = current_app.config['ADMIN_CLIENT_USER_NAME']
    secret = current_app.config['INTERNAL_CLIENT_API_KEYS'][client_id][0]

    token = create_jwt_token(secret, client_id)
    response = client.get('/service', headers={'Authorization': 'Bearer {}'.format(token)})
    assert response.status_code == 200


def test_should_allow_valid_token_for_request_with_path_params_for_admin_url_with_second_secret(client):
    client_id = current_app.config['ADMIN_CLIENT_USER_NAME']
    new_secrets = { client_id: ["secret1", "secret2"] }

    with set_config(client.application, 'INTERNAL_CLIENT_API_KEYS', new_secrets):
        token = create_jwt_token("secret1", client_id)
        response = client.get('/service', headers={'Authorization': 'Bearer {}'.format(token)})
        assert response.status_code == 200

        token = create_jwt_token("secret2", client_id)
        response = client.get('/service', headers={'Authorization': 'Bearer {}'.format(token)})
        assert response.status_code == 200


def test_should_allow_valid_token_when_service_has_multiple_keys(client, sample_api_key):
    data = {'service': sample_api_key.service,
            'name': 'some key name',
            'created_by': sample_api_key.created_by,
            'key_type': KEY_TYPE_NORMAL
            }
    api_key = ApiKey(**data)
    save_model_api_key(api_key)
    token = __create_token(sample_api_key.service_id)
    response = client.get(
        '/notifications',
        headers={'Authorization': 'Bearer {}'.format(token)})
    assert response.status_code == 200


def test_authentication_passes_when_service_has_multiple_keys_some_expired(
        client,
        sample_api_key):
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
        '/notifications',
        headers={'Authorization': 'Bearer {}'.format(token)})
    assert response.status_code == 200


def test_authentication_returns_token_expired_when_service_uses_expired_key_and_has_multiple_keys(client,
                                                                                                  sample_api_key):
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
    request.headers = {'Authorization': 'Bearer {}'.format(token)}
    with pytest.raises(AuthError) as exc:
        requires_auth()
    assert exc.value.short_message == 'Invalid token: API key revoked'
    assert exc.value.service_id == str(expired_api_key.service_id)
    assert exc.value.api_key_id == expired_api_key.id


def test_authentication_returns_error_when_admin_client_has_no_secrets(client):
    client_id = current_app.config.get('ADMIN_CLIENT_USER_NAME')
    secret = current_app.config.get('INTERNAL_CLIENT_API_KEYS')[client_id][0]
    token = create_jwt_token(secret, client_id)
    new_secrets = { client_id: [] }

    with set_config(client.application, 'INTERNAL_CLIENT_API_KEYS', new_secrets):
        response = client.get(
            '/service',
            headers={'Authorization': 'Bearer {}'.format(token)})

    assert response.status_code == 401
    error_message = json.loads(response.get_data())
    assert error_message['message'] == {"token": ["Unauthorized: API authentication token not found"]}


def test_authentication_returns_error_when_admin_client_secret_is_invalid(client):
    client_id = current_app.config.get('ADMIN_CLIENT_USER_NAME')
    secret = current_app.config.get('INTERNAL_CLIENT_API_KEYS')[client_id][0]
    token = create_jwt_token(secret, client_id)
    new_secrets = { client_id:  ['something-wrong'] }

    with set_config(client.application, 'INTERNAL_CLIENT_API_KEYS', new_secrets):
        response = client.get(
            '/service',
            headers={'Authorization': 'Bearer {}'.format(token)})

    assert response.status_code == 401
    error_message = json.loads(response.get_data())
    assert error_message['message'] == {"token": ["Unauthorized: API authentication token not found"]}


def test_authentication_returns_error_when_service_doesnt_exit(
    client,
    sample_api_key
):
    # get service ID and secret the wrong way around
    token = create_jwt_token(
        secret=str(sample_api_key.service_id),
        client_id=str(sample_api_key.id))

    response = client.get(
        '/notifications',
        headers={'Authorization': 'Bearer {}'.format(token)}
    )
    assert response.status_code == 403
    error_message = json.loads(response.get_data())
    assert error_message['message'] == {'token': ['Invalid token: service not found']}


def test_authentication_returns_error_when_service_inactive(client, sample_api_key):
    sample_api_key.service.active = False
    token = create_jwt_token(secret=str(sample_api_key.id), client_id=str(sample_api_key.service_id))

    response = client.get('/notifications', headers={'Authorization': 'Bearer {}'.format(token)})

    assert response.status_code == 403
    error_message = json.loads(response.get_data())
    assert error_message['message'] == {'token': ['Invalid token: service is archived']}


def test_authentication_returns_error_when_service_has_no_secrets(client,
                                                                  sample_service,
                                                                  fake_uuid):
    token = create_jwt_token(
        secret=fake_uuid,
        client_id=str(sample_service.id))

    request.headers = {'Authorization': 'Bearer {}'.format(token)}
    with pytest.raises(AuthError) as exc:
        requires_auth()
    assert exc.value.short_message == 'Invalid token: service has no API keys'
    assert exc.value.service_id == str(sample_service.id)


def test_should_attach_the_current_api_key_to_current_app(notify_api, sample_service, sample_api_key):
    with notify_api.test_request_context(), notify_api.test_client() as client:
        token = __create_token(sample_api_key.service_id)
        response = client.get(
            '/notifications',
            headers={'Authorization': 'Bearer {}'.format(token)}
        )
        assert response.status_code == 200
        assert str(api_user.id) == str(sample_api_key.id)


def test_should_return_403_when_token_is_expired(client,
                                                 sample_api_key):
    with freeze_time('2001-01-01T12:00:00'):
        token = __create_token(sample_api_key.service_id)
    with freeze_time('2001-01-01T12:00:40'):
        with pytest.raises(AuthError) as exc:
            request.headers = {'Authorization': 'Bearer {}'.format(token)}
            requires_auth()
    assert exc.value.short_message == 'Error: Your system clock must be accurate to within 30 seconds'
    assert exc.value.service_id == str(sample_api_key.service_id)
    assert str(exc.value.api_key_id) == str(sample_api_key.id)


def __create_token(service_id):
    return create_jwt_token(secret=get_unsigned_secrets(service_id)[0],
                            client_id=str(service_id))


@pytest.mark.parametrize('check_proxy_header,header_value,expected_status', [
    (True, 'key_1', 200),
    (True, 'wrong_key', 200),
    (False, 'key_1', 200),
    (False, 'wrong_key', 200),
])
def test_proxy_key_non_auth_endpoint(notify_api, check_proxy_header, header_value, expected_status):
    with set_config_values(notify_api, {
        'ROUTE_SECRET_KEY_1': 'key_1',
        'ROUTE_SECRET_KEY_2': '',
        'CHECK_PROXY_HEADER': check_proxy_header,
    }):

        with notify_api.test_client() as client:
            response = client.get(
                path='/_status',
                headers=[
                    ('X-Custom-Forwarder', header_value),
                ]
            )
        assert response.status_code == expected_status


@pytest.mark.parametrize('check_proxy_header,header_value,expected_status', [
    (True, 'key_1', 200),
    (True, 'wrong_key', 403),
    (False, 'key_1', 200),
    (False, 'wrong_key', 200),
])
def test_proxy_key_on_admin_auth_endpoint(notify_api, check_proxy_header, header_value, expected_status):
    client_id = current_app.config.get('ADMIN_CLIENT_USER_NAME')
    secret = current_app.config.get('INTERNAL_CLIENT_API_KEYS')[client_id][0]
    token = create_jwt_token(secret, client_id)

    with set_config_values(notify_api, {
        'ROUTE_SECRET_KEY_1': 'key_1',
        'ROUTE_SECRET_KEY_2': '',
        'CHECK_PROXY_HEADER': check_proxy_header,
    }):

        with notify_api.test_client() as client:
            response = client.get(
                path='/service',
                headers=[
                    ('X-Custom-Forwarder', header_value),
                    ('Authorization', 'Bearer {}'.format(token))
                ]
            )
        assert response.status_code == expected_status


def test_should_cache_service_and_api_key_lookups(mocker, client, sample_api_key):

    mock_get_api_keys = mocker.patch(
        'app.serialised_models.get_model_api_keys',
        wraps=get_model_api_keys,
    )
    mock_get_service = mocker.patch(
        'app.serialised_models.dao_fetch_service_by_id',
        wraps=dao_fetch_service_by_id,
    )

    for _ in range(5):
        token = __create_token(sample_api_key.service_id)
        client.get('/notifications', headers={
            'Authorization': f'Bearer {token}'
        })

    assert mock_get_api_keys.call_args_list == [
        call(str(sample_api_key.service_id))
    ]
    assert mock_get_service.call_args_list == [
        call(sample_api_key.service_id)
    ]
