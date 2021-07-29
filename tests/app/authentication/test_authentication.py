import time
import uuid
from unittest.mock import call

import jwt
import pytest
from flask import current_app, json, request
from notifications_python_client.authentication import create_jwt_token

from app import api_user
from app.authentication.auth import (
    GENERAL_TOKEN_ERROR_MESSAGE,
    AuthError,
    _decode_jwt_token,
    _get_auth_token,
    _get_token_issuer,
)
from app.dao.api_key_dao import (
    expire_api_key,
    get_model_api_keys,
    get_unsigned_secrets,
)
from app.dao.services_dao import dao_fetch_service_by_id
from tests.conftest import set_config_values


def create_custom_jwt_token(headers=None, payload=None, key=None):
    # code copied from notifications_python_client.authentication.py::create_jwt_token
    headers = headers or {"typ": 'JWT', "alg": 'HS256'}
    return jwt.encode(payload=payload, key=key or str(uuid.uuid4()), headers=headers)


@pytest.fixture
def service_jwt_secret(sample_api_key):
    return get_unsigned_secrets(sample_api_key.service_id)[0]


@pytest.fixture
def service_jwt_token(sample_api_key, service_jwt_secret):
    return create_jwt_token(
        secret=service_jwt_secret,
        client_id=str(sample_api_key.service_id),
    )


@pytest.fixture
def admin_jwt_token():
    admin_jwt_client_id = current_app.config['ADMIN_CLIENT_USER_NAME']
    admin_jwt_secret = current_app.config['INTERNAL_CLIENT_API_KEYS'][admin_jwt_client_id][0]
    return create_jwt_token(admin_jwt_secret, admin_jwt_client_id)


def test_requires_auth_should_allow_valid_token_for_request_with_path_params_for_public_url(
    client,
    service_jwt_token,
):
    response = client.get('/notifications', headers={'Authorization': 'Bearer {}'.format(service_jwt_token)})
    assert response.status_code == 200


def test_requires_admin_auth_should_allow_valid_token_for_request_with_path_params(
    client,
    admin_jwt_token
):
    response = client.get('/service', headers={'Authorization': 'Bearer {}'.format(admin_jwt_token)})
    assert response.status_code == 200


def test_get_auth_token_should_not_allow_request_with_no_token(client):
    request.headers = {}
    with pytest.raises(AuthError) as exc:
        _get_auth_token(request)
    assert exc.value.short_message == 'Unauthorized: authentication token must be provided'


def test_get_auth_token_should_not_allow_request_with_incorrect_header(client):
    request.headers = {'Authorization': 'Basic 1234'}
    with pytest.raises(AuthError) as exc:
        _get_auth_token(request)
    assert exc.value.short_message == 'Unauthorized: authentication bearer scheme must be used'


@pytest.mark.parametrize('scheme', ['bearer', 'Bearer'])
def test_get_auth_token_should_allow_valid_token(client, scheme):
    token = create_jwt_token(client_id='something', secret='secret')
    request.headers = {'Authorization': '{} {}'.format(scheme, token)}
    assert _get_auth_token(request) == token


def test_get_token_issuer_should_not_allow_request_with_incorrect_token(client):
    with pytest.raises(AuthError) as exc:
        _get_token_issuer("Bearer 1234")
    assert exc.value.short_message == GENERAL_TOKEN_ERROR_MESSAGE


def test_get_token_issuer_should_not_allow_request_with_no_iss(client):
    token = create_custom_jwt_token(
        payload={'iat': int(time.time())}
    )

    with pytest.raises(AuthError) as exc:
        _get_token_issuer(token)
    assert exc.value.short_message == 'Invalid token: iss field not provided'


def test_decode_jwt_token_should_not_allow_non_hs256_algorithm(client, sample_api_key):
    token = create_custom_jwt_token(
        headers={"typ": 'JWT', "alg": 'HS512'},
        payload={},
    )

    with pytest.raises(AuthError) as exc:
        _decode_jwt_token(token, [sample_api_key])
    assert exc.value.short_message == 'Invalid token: algorithm used is not HS256'


def test_decode_jwt_token_should_not_allow_no_iat(
    client,
    sample_api_key,
):
    token = create_custom_jwt_token(
        payload={'iss': 'something'}
    )

    with pytest.raises(AuthError) as exc:
        _decode_jwt_token(token, [sample_api_key])
    assert exc.value.short_message == "Invalid token: API key not found"


def test_decode_jwt_token_should_not_allow_old_iat(
    client,
    sample_api_key,
):
    token = create_custom_jwt_token(
        payload={'iss': 'something', 'iat': int(time.time()) - 60},
        key=sample_api_key.secret,
    )

    with pytest.raises(AuthError) as exc:
        _decode_jwt_token(token, [sample_api_key])
    assert exc.value.short_message == "Error: Your system clock must be accurate to within 30 seconds"


def test_decode_jwt_token_should_not_allow_extra_claims(
    client,
    sample_api_key,
):
    token = create_custom_jwt_token(
        payload={
            'iss': 'something',
            'iat': int(time.time()),
            'aud': 'notifications.service.gov.uk'  # extra claim that we don't support
        },
        key=sample_api_key.secret,
    )

    with pytest.raises(AuthError) as exc:
        _decode_jwt_token(token, [sample_api_key])
    assert exc.value.short_message == GENERAL_TOKEN_ERROR_MESSAGE


def test_decode_jwt_token_should_not_allow_invalid_secret(
    client,
    sample_api_key
):
    token = create_jwt_token(
        secret="not-so-secret",
        client_id=str(sample_api_key.service_id)
    )

    with pytest.raises(AuthError) as exc:
        _decode_jwt_token(token, [sample_api_key])
    assert exc.value.short_message == 'Invalid token: API key not found'


def test_decode_jwt_token_should_allow_multiple_api_keys(
    client,
    sample_api_key,
    sample_test_api_key,
):
    token = create_jwt_token(
        secret=sample_test_api_key.secret,
        client_id=str(sample_test_api_key.service_id),
    )

    # successful if no error is raised
    _decode_jwt_token(token, [sample_api_key, sample_test_api_key])


def test_decode_jwt_token_should_allow_some_expired_keys(
    client,
    sample_api_key,
    sample_test_api_key,
):
    expire_api_key(sample_api_key.service_id, sample_api_key.id)

    token = create_jwt_token(
        secret=sample_test_api_key.secret,
        client_id=str(sample_test_api_key.service_id),
    )

    # successful if no error is raised
    _decode_jwt_token(token, [sample_api_key, sample_test_api_key])


def test_decode_jwt_token_errors_when_all_api_keys_are_expired(
    client,
    sample_api_key,
    sample_test_api_key,
):
    expire_api_key(sample_api_key.service_id, sample_api_key.id)
    expire_api_key(sample_test_api_key.service_id, sample_test_api_key.id)

    token = create_jwt_token(
        secret=sample_test_api_key.secret,
        client_id=str(sample_test_api_key.service_id),
    )

    with pytest.raises(AuthError) as exc:
        _decode_jwt_token(token, [sample_api_key, sample_test_api_key], service_id='1234')

    assert exc.value.short_message == 'Invalid token: API key revoked'
    assert exc.value.service_id == '1234'
    assert exc.value.api_key_id == sample_test_api_key.id


def test_decode_jwt_token_returns_error_with_no_secrets(client):
    with pytest.raises(AuthError) as exc:
        _decode_jwt_token('token', [])
    assert exc.value.short_message == "Invalid token: API key not found"


@pytest.mark.parametrize('service_id', ['not-a-valid-id', 1234])
def test_requires_auth_should_not_allow_service_id_with_the_wrong_data_type(
    client,
    service_jwt_secret,
    service_id
):
    token = create_jwt_token(
        client_id=service_id,
        secret=service_jwt_secret,
    )
    response = client.get(
        '/notifications',
        headers={'Authorization': "Bearer {}".format(token)}
    )
    assert response.status_code == 403
    data = json.loads(response.get_data())
    assert data['message'] == {"token": ['Invalid token: service id is not the right data type']}


def test_requires_auth_returns_error_when_service_doesnt_exist(
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


def test_requires_auth_returns_error_when_service_inactive(
    client,
    sample_api_key,
    service_jwt_token,
):
    sample_api_key.service.active = False
    response = client.get('/notifications', headers={'Authorization': 'Bearer {}'.format(service_jwt_token)})

    assert response.status_code == 403
    error_message = json.loads(response.get_data())
    assert error_message['message'] == {'token': ['Invalid token: service is archived']}


def test_should_attach_the_current_api_key_to_current_app(
    notify_api,
    sample_service,
    sample_api_key,
    service_jwt_token,
):
    with notify_api.test_request_context(), notify_api.test_client() as client:
        response = client.get(
            '/notifications',
            headers={'Authorization': 'Bearer {}'.format(service_jwt_token)}
        )
        assert response.status_code == 200
        assert str(api_user.id) == str(sample_api_key.id)


@pytest.mark.parametrize('check_proxy_header,header_value', [
    (True, 'key_1'),
    (True, 'wrong_key'),
    (False, 'key_1'),
    (False, 'wrong_key'),
])
def test_requires_no_auth_proxy_key(notify_api, check_proxy_header, header_value):
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
        assert response.status_code == 200


@pytest.mark.parametrize('check_proxy_header,header_value,expected_status', [
    (True, 'key_1', 200),
    (True, 'wrong_key', 403),
    (False, 'key_1', 200),
    (False, 'wrong_key', 200),
])
def test_requires_admin_auth_proxy_key(
    notify_api,
    check_proxy_header,
    header_value,
    expected_status,
    admin_jwt_token,
):
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
                    ('Authorization', 'Bearer {}'.format(admin_jwt_token))
                ]
            )
        assert response.status_code == expected_status


def test_requires_auth_should_cache_service_and_api_key_lookups(
    mocker,
    client,
    sample_api_key,
    service_jwt_token
):
    mock_get_api_keys = mocker.patch(
        'app.serialised_models.get_model_api_keys',
        wraps=get_model_api_keys,
    )
    mock_get_service = mocker.patch(
        'app.serialised_models.dao_fetch_service_by_id',
        wraps=dao_fetch_service_by_id,
    )

    for _ in range(5):
        client.get('/notifications', headers={
            'Authorization': f'Bearer {service_jwt_token}'
        })

    assert mock_get_api_keys.call_args_list == [
        call(str(sample_api_key.service_id))
    ]
    assert mock_get_service.call_args_list == [
        call(sample_api_key.service_id)
    ]
