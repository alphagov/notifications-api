import uuid

from flask import current_app, g, request
from gds_metrics import Histogram
from notifications_python_client.authentication import (
    decode_jwt_token,
    get_token_issuer,
)
from notifications_python_client.errors import (
    TokenAlgorithmError,
    TokenDecodeError,
    TokenError,
    TokenExpiredError,
    TokenIssuerError,
)
from notifications_utils import request_helper
from sqlalchemy.orm.exc import NoResultFound

from app.serialised_models import SerialisedService

GENERAL_TOKEN_ERROR_MESSAGE = 'Invalid token: make sure your API token matches the example at https://docs.notifications.service.gov.uk/rest-api.html#authorisation-header'  # noqa

AUTH_DB_CONNECTION_DURATION_SECONDS = Histogram(
    'auth_db_connection_duration_seconds',
    'Time taken to get DB connection and fetch service from database',
)


class AuthError(Exception):
    def __init__(self, message, code, service_id=None, api_key_id=None):
        self.message = {"token": [message]}
        self.short_message = message
        self.code = code
        self.service_id = service_id
        self.api_key_id = api_key_id

    def __str__(self):
        return 'AuthError({message}, {code}, service_id={service_id}, api_key_id={api_key_id})'.format(**self.__dict__)

    def to_dict_v2(self):
        return {
            'status_code': self.code,
            "errors": [
                {
                    "error": "AuthError",
                    "message": self.short_message
                }
            ]
        }


def get_auth_token(req):
    auth_header = req.headers.get('Authorization', None)
    if not auth_header:
        raise AuthError('Unauthorized: authentication token must be provided', 401)

    auth_scheme = auth_header[:7].title()

    if auth_scheme != 'Bearer ':
        raise AuthError('Unauthorized: authentication bearer scheme must be used', 401)

    return auth_header[7:]


def requires_no_auth():
    pass


def requires_admin_auth():
    requires_internal_auth(current_app.config.get('ADMIN_CLIENT_USER_NAME'))


def requires_internal_auth(expected_client_id):
    if expected_client_id not in current_app.config.get('INTERNAL_CLIENT_API_KEYS'):
        raise TypeError("Unknown client_id for internal auth")

    request_helper.check_proxy_header_before_request()
    auth_token = get_auth_token(request)
    client_id = __get_token_issuer(auth_token)

    if client_id != expected_client_id:
        raise AuthError("Unauthorized: not allowed to perform this action", 401)

    g.service_id = client_id
    secrets = current_app.config.get('INTERNAL_CLIENT_API_KEYS')[client_id]

    for secret in secrets:
        try:
            decode_jwt_token(auth_token, secret)
            return
        except TokenExpiredError:
            raise AuthError("Invalid token: expired, check that your system clock is accurate", 403)
        except TokenDecodeError:
            # TODO: Change this so it doesn't also catch `TokenIssuerError` or `TokenIssuedAtError` exceptions
            # (which are children of `TokenDecodeError`) as these should cause an auth error immediately rather
            # than continue on to check the next admin client secret
            continue

    # Either there are no admin client secrets or their token didn't match one of them so error
    raise AuthError("Unauthorized: API authentication token not found", 401)


def requires_auth():
    request_helper.check_proxy_header_before_request()

    auth_token = get_auth_token(request)
    issuer = __get_token_issuer(auth_token)  # ie the `iss` claim which should be a service ID

    try:
        service_id = uuid.UUID(issuer)
    except Exception:
        raise AuthError("Invalid token: service id is not the right data type", 403)

    try:
        with AUTH_DB_CONNECTION_DURATION_SECONDS.time():
            service = SerialisedService.from_id(service_id)
    except NoResultFound:
        raise AuthError("Invalid token: service not found", 403)

    if not service.api_keys:
        raise AuthError("Invalid token: service has no API keys", 403, service_id=service.id)

    if not service.active:
        raise AuthError("Invalid token: service is archived", 403, service_id=service.id)

    for api_key in service.api_keys:
        try:
            decode_jwt_token(auth_token, api_key.secret)
        except TokenExpiredError:
            err_msg = "Error: Your system clock must be accurate to within 30 seconds"
            raise AuthError(err_msg, 403, service_id=service.id, api_key_id=api_key.id)
        except TokenAlgorithmError:
            err_msg = "Invalid token: algorithm used is not HS256"
            raise AuthError(err_msg, 403, service_id=service.id, api_key_id=api_key.id)
        except TokenDecodeError:
            # we attempted to validate the token but it failed meaning it was not signed using this api key.
            # Let's try the next one
            # TODO: Change this so it doesn't also catch `TokenIssuerError` or `TokenIssuedAtError` exceptions (which
            # are children of `TokenDecodeError`) as these should cause an auth error immediately rather than
            # continue on to check the next API key
            continue
        except TokenError:
            # General error when trying to decode and validate the token
            raise AuthError(GENERAL_TOKEN_ERROR_MESSAGE, 403, service_id=service.id, api_key_id=api_key.id)

        if api_key.expiry_date:
            raise AuthError("Invalid token: API key revoked", 403, service_id=service.id, api_key_id=api_key.id)

        g.service_id = service.id
        g.api_user = api_key
        g.authenticated_service = service

        current_app.logger.info('API authorised for service {} with api key {}, using issuer {} for URL: {}'.format(
            service.id,
            api_key.id,
            request.headers.get('User-Agent'),
            request.base_url
        ))
        return
    else:
        # service has API keys, but none matching the one the user provided
        raise AuthError("Invalid token: API key not found", 403, service_id=service.id)


def __get_token_issuer(auth_token):
    try:
        issuer = get_token_issuer(auth_token)
    except TokenIssuerError:
        raise AuthError("Invalid token: iss field not provided", 403)
    except TokenDecodeError:
        raise AuthError(GENERAL_TOKEN_ERROR_MESSAGE, 403)
    return issuer
