import jwt
import uuid
import time
from datetime import datetime

import pytest
import flask
from flask import json, current_app
from freezegun import freeze_time
from notifications_python_client.authentication import create_jwt_token

from app import api_user
from app.dao.api_key_dao import get_unsigned_secrets, save_model_api_key, get_unsigned_secret, expire_api_key
from app.models import ApiKey, KEY_TYPE_NORMAL
from app.authentication.auth import restrict_ip_sms, AuthError


# Test the require_admin_auth and require_auth methods
@pytest.mark.parametrize('url', ['/service', '/notifications'])
def test_should_not_allow_request_with_no_token(client, url):
    response = client.get(url)
    assert response.status_code == 401
    data = json.loads(response.get_data())
    assert data['message'] == {"token": ['Unauthorized, authentication token must be provided']}


@pytest.mark.parametrize('url', ['/service', '/notifications'])
def test_should_not_allow_request_with_incorrect_header(client, url):
    response = client.get(url, headers={'Authorization': 'Basic 1234'})
    assert response.status_code == 401
    data = json.loads(response.get_data())
    assert data['message'] == {"token": ['Unauthorized, authentication bearer scheme must be used']}


@pytest.mark.parametrize('url', ['/service', '/notifications'])
def test_should_not_allow_request_with_incorrect_token(client, url):
    response = client.get(url, headers={'Authorization': 'Bearer 1234'})
    assert response.status_code == 403
    data = json.loads(response.get_data())
    assert data['message'] == {"token": ['Invalid token: signature, api token is not valid']}


@pytest.mark.parametrize('url', ['/service', '/notifications'])
def test_should_not_allow_request_with_no_iss(client, url):
    # code copied from notifications_python_client.authentication.py::create_jwt_token
    headers = {
        "typ": 'JWT',
        "alg": 'HS256'
    }

    claims = {
        # 'iss': not provided
        'iat': int(time.time())
    }

    token = jwt.encode(payload=claims, key=str(uuid.uuid4()), headers=headers).decode()

    response = client.get(url, headers={'Authorization': 'Bearer {}'.format(token)})
    assert response.status_code == 403
    data = json.loads(response.get_data())
    assert data['message'] == {"token": ['Invalid token: iss field not provided']}


@pytest.mark.parametrize('url, auth_method',
                         [('/service', 'requires_admin_auth'),
                          ('/notifications', 'requires_auth')])
def test_should_not_allow_request_with_no_iat(client, sample_api_key, url, auth_method):
    if auth_method == 'requires_admin_auth':
        iss = current_app.config['ADMIN_CLIENT_USER_NAME']
    if auth_method == 'requires_auth':
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

    token = jwt.encode(payload=claims, key=str(uuid.uuid4()), headers=headers).decode()

    response = client.get(url, headers={'Authorization': 'Bearer {}'.format(token)})
    assert response.status_code == 403
    data = json.loads(response.get_data())
    assert data['message'] == {"token": ['Invalid token: signature, api token is not valid']}


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
    assert data['message'] == {"token": ['Invalid token: signature, api token is not valid']}


@pytest.mark.parametrize('scheme', ['bearer', 'Bearer'])
def test_should_allow_valid_token(client, sample_api_key, scheme):
    token = __create_token(sample_api_key.service_id)
    response = client.get('/notifications', headers={'Authorization': '{} {}'.format(scheme, token)})
    assert response.status_code == 200


def test_should_not_allow_service_id_that_is_not_the_wrong_data_type(client, sample_api_key):
    token = create_jwt_token(secret=get_unsigned_secrets(sample_api_key.service_id)[0],
                             client_id=str('not-a-valid-id'))
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
    token = create_jwt_token(current_app.config['ADMIN_CLIENT_SECRET'], current_app.config['ADMIN_CLIENT_USER_NAME'])
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
        '/notifications'.format(str(sample_api_key.service_id)),
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
    response = client.get(
        '/notifications',
        headers={'Authorization': 'Bearer {}'.format(token)})
    assert response.status_code == 403
    data = json.loads(response.get_data())
    assert data['message'] == {"token": ['Invalid token: API key revoked']}


def test_authentication_returns_error_when_admin_client_has_no_secrets(client):
    api_secret = current_app.config.get('ADMIN_CLIENT_SECRET')
    token = create_jwt_token(
        secret=api_secret,
        client_id=current_app.config.get('ADMIN_CLIENT_USER_NAME')
    )
    current_app.config['ADMIN_CLIENT_SECRET'] = ''
    response = client.get(
        '/service',
        headers={'Authorization': 'Bearer {}'.format(token)})
    assert response.status_code == 403
    error_message = json.loads(response.get_data())
    assert error_message['message'] == {"token": ["Invalid token: signature, api token is not valid"]}
    current_app.config['ADMIN_CLIENT_SECRET'] = api_secret


def test_authentication_returns_error_when_admin_client_secret_is_invalid(client):
    api_secret = current_app.config.get('ADMIN_CLIENT_SECRET')
    token = create_jwt_token(
        secret=api_secret,
        client_id=current_app.config.get('ADMIN_CLIENT_USER_NAME')
    )
    current_app.config['ADMIN_CLIENT_SECRET'] = 'something-wrong'
    response = client.get(
        '/service',
        headers={'Authorization': 'Bearer {}'.format(token)})
    assert response.status_code == 403
    error_message = json.loads(response.get_data())
    assert error_message['message'] == {"token": ["Invalid token: signature, api token is not valid"]}
    current_app.config['ADMIN_CLIENT_SECRET'] = api_secret


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

    response = client.get(
        '/notifications',
        headers={'Authorization': 'Bearer {}'.format(token)})
    assert response.status_code == 403
    error_message = json.loads(response.get_data())
    assert error_message['message'] == {'token': ['Invalid token: service has no API keys']}


def test_should_attach_the_current_api_key_to_current_app(notify_api, sample_service, sample_api_key):
    with notify_api.test_request_context() as context, notify_api.test_client() as client:
        token = __create_token(sample_api_key.service_id)
        response = client.get(
            '/notifications',
            headers={'Authorization': 'Bearer {}'.format(token)}
        )
        assert response.status_code == 200
        assert api_user == sample_api_key


def test_should_return_403_when_token_is_expired(client,
                                                 sample_api_key):
    with freeze_time('2001-01-01T12:00:00'):
        token = __create_token(sample_api_key.service_id)
    with freeze_time('2001-01-01T12:00:40'):
        response = client.get(
            '/notifications',
            headers={'Authorization': 'Bearer {}'.format(token)})
    assert response.status_code == 403
    error_message = json.loads(response.get_data())
    assert error_message['message'] == {'token': [
        'Invalid token: expired, check that your system clock is accurate'
    ]}


def __create_token(service_id):
    return create_jwt_token(secret=get_unsigned_secrets(service_id)[0],
                            client_id=str(service_id))


@pytest.fixture
def restrict_ip_sms_app():
    app = flask.Flask(__name__)
    app.config['TESTING'] = True
    app.config['SMS_INBOUND_WHITELIST'] = ['111.111.111.111', '100.100.100.100']
    blueprint = flask.Blueprint('restrict_ip_sms_app', __name__)

    @blueprint.route('/')
    def test_endpoint():
        return 'OK', 200

    blueprint.before_request(restrict_ip_sms)
    app.register_blueprint(blueprint)

    with app.test_request_context(), app.test_client() as client:
        yield client


def test_allow_valid_ips(restrict_ip_sms_app):
    response = restrict_ip_sms_app.get(
        path='/',
        headers=[
            ('X-Forwarded-For', '111.111.111.111, 222.222.222.222, 127.0.0.1'),
        ]
    )

    assert response.status_code == 200


@pytest.mark.xfail(reason='Currently not blocking invalid IPs', strict=True)
def test_reject_invalid_ips(restrict_ip_sms_app):
    with pytest.raises(AuthError) as exc_info:
        restrict_ip_sms_app.get(
            path='/',
            headers=[
                ('X-Forwarded-For', '222.222.222.222, 333.333.333.333, 127.0.0.1')
            ]
        )

    assert exc_info.value.short_message == 'Unknown source IP address from the SMS provider'


@pytest.mark.xfail(reason='Currently not blocking invalid senders', strict=True)
def test_illegitimate_ips(restrict_ip_sms_app):
    with pytest.raises(AuthError) as exc_info:
        restrict_ip_sms_app.get(
            path='/',
            headers=[
                ('X-Forwarded-For', '111.111.111.111, 999.999.999.999, 333.333.333.333, 127.0.0.1')
            ]
        )

    assert exc_info.value.short_message == 'Unknown IP route not from known SMS provider'
