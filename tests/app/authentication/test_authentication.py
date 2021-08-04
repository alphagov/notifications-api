import time
import uuid

import jwt
import pytest
from flask import current_app, g, request
from notifications_python_client.authentication import create_jwt_token

from app import db
from app.authentication.auth import (
    GENERAL_TOKEN_ERROR_MESSAGE,
    AuthError,
    _decode_jwt_token,
    _get_auth_token,
    _get_token_issuer,
    requires_auth,
    requires_internal_auth,
)
from app.dao.api_key_dao import (
    expire_api_key,
    get_model_api_keys,
    get_unsigned_secrets,
)
from app.dao.services_dao import dao_fetch_service_by_id
from tests import (
    create_admin_authorization_header,
    create_internal_authorization_header,
    create_service_authorization_header,
)
from tests.conftest import set_config_values


@pytest.fixture
def internal_jwt_token(notify_api):
    with set_config_values(notify_api, {
        'INTERNAL_CLIENT_API_KEYS': {
            'my-internal-app': ['my-internal-app-secret'],
        }
    }):
        yield create_jwt_token(
            client_id='my-internal-app',
            secret='my-internal-app-secret'
        )


def requires_my_internal_app_auth():
    requires_internal_auth('my-internal-app')


def create_custom_jwt_token(headers=None, payload=None, secret=None):
    # code copied from notifications_python_client.authentication.py::create_jwt_token
    headers = headers or {"typ": 'JWT', "alg": 'HS256'}
    return jwt.encode(payload=payload, key=secret or str(uuid.uuid4()), headers=headers)


@pytest.fixture
def service_jwt_secret(sample_api_key):
    return get_unsigned_secrets(sample_api_key.service_id)[0]


@pytest.fixture
def service_jwt_token(sample_api_key, service_jwt_secret):
    return create_jwt_token(
        secret=service_jwt_secret,
        client_id=str(sample_api_key.service_id),
    )


def test_requires_auth_should_allow_valid_token_for_request(client, sample_api_key):
    header = create_service_authorization_header(sample_api_key.service_id)
    response = client.get('/notifications', headers=[header])
    assert response.status_code == 200


def test_requires_admin_auth_should_allow_valid_token_for_request(client):
    header = create_admin_authorization_header()
    response = client.get('/service', headers=[header])
    assert response.status_code == 200


def test_requires_govuk_alerts_auth_should_allow_valid_token_for_request(client):
    jwt_client_id = current_app.config['GOVUK_ALERTS_CLIENT_ID']
    header = create_internal_authorization_header(jwt_client_id)
    response = client.get('/v2/govuk-alerts', headers=[header])
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
        secret=sample_api_key.secret,
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
        secret=sample_api_key.secret,
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

    request.headers = {'Authorization': "Bearer {}".format(token)}
    with pytest.raises(AuthError) as exc:
        requires_auth()
    assert exc.value.short_message == 'Invalid token: service id is not the right data type'


def test_requires_auth_returns_error_when_service_doesnt_exist(
    client,
    sample_api_key
):
    # get service ID and secret the wrong way around
    token = create_jwt_token(
        secret=str(sample_api_key.service_id),
        client_id=str(sample_api_key.id),
    )

    request.headers = {'Authorization': 'Bearer {}'.format(token)}
    with pytest.raises(AuthError) as exc:
        requires_auth()
    assert exc.value.short_message == 'Invalid token: service not found'


def test_requires_auth_returns_error_when_service_inactive(
    client,
    sample_api_key,
    service_jwt_token,
):
    sample_api_key.service.active = False

    request.headers = {'Authorization': 'Bearer {}'.format(service_jwt_token)}
    with pytest.raises(AuthError) as exc:
        requires_auth()
    assert exc.value.short_message == 'Invalid token: service is archived'


def test_requires_auth_should_assign_global_variables(
    client,
    sample_api_key,
    service_jwt_token,
):
    request.headers = {'Authorization': 'Bearer {}'.format(service_jwt_token)}
    requires_auth()
    assert g.api_user.id == sample_api_key.id
    assert g.service_id == sample_api_key.service_id
    assert g.authenticated_service.id == str(sample_api_key.service_id)


def test_requires_auth_errors_if_service_has_no_api_keys(
    client,
    sample_api_key,
    service_jwt_token,
):
    db.session.delete(sample_api_key)
    request.headers = {'Authorization': 'Bearer {}'.format(service_jwt_token)}
    with pytest.raises(AuthError) as exc:
        requires_auth()
    assert exc.value.short_message == 'Invalid token: service has no API keys'


def test_requires_auth_should_cache_service_and_api_key_lookups(
    mocker,
    client,
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

    request.headers = {'Authorization': f'Bearer {service_jwt_token}'}
    requires_auth()
    requires_auth()  # second request

    mock_get_api_keys.assert_called_once()
    mock_get_service.assert_called_once()


def test_requires_internal_auth_checks_proxy_key(
    client,
    mocker,
    internal_jwt_token,
):
    proxy_check_mock = mocker.patch(
        'app.authentication.auth.request_helper.check_proxy_header_before_request'
    )

    request.headers = {'Authorization': 'Bearer {}'.format(internal_jwt_token)}
    requires_my_internal_app_auth()
    proxy_check_mock.assert_called_once()


def test_requires_internal_auth_errors_for_unknown_app(client):
    with pytest.raises(TypeError) as exc:
        requires_internal_auth('another-app')
    assert str(exc.value) == 'Unknown client_id for internal auth'


def test_requires_internal_auth_errors_for_api_app_mismatch(
    client,
    internal_jwt_token,
    service_jwt_token
):
    request.headers = {'Authorization': 'Bearer {}'.format(service_jwt_token)}
    with pytest.raises(AuthError) as exc:
        requires_my_internal_app_auth()
    assert exc.value.short_message == 'Unauthorized: not allowed to perform this action'


def test_requires_internal_auth_sets_global_variables(
    client,
    internal_jwt_token,
):
    request.headers = {'Authorization': 'Bearer {}'.format(internal_jwt_token)}
    requires_my_internal_app_auth()
    assert g.service_id == 'my-internal-app'
