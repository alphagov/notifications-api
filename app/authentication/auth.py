from flask import request, _request_ctx_stack, current_app, g
from notifications_python_client.authentication import decode_jwt_token, get_token_issuer
from notifications_python_client.errors import (
    TokenDecodeError, TokenExpiredError, TokenIssuerError, TokenAlgorithmError, TokenError
)
from notifications_utils import request_helper
from sqlalchemy.exc import DataError
from sqlalchemy.orm.exc import NoResultFound

from app.dao.services_dao import dao_fetch_service_by_id_with_api_keys


GENERAL_TOKEN_ERROR_MESSAGE = 'Invalid token: make sure your API token matches the example at https://docs.notifications.service.gov.uk/rest-api.html#authorisation-header'  # noqa


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
    request_helper.check_proxy_header_before_request()

    auth_token = get_auth_token(request)
    client = __get_token_issuer(auth_token)

    if client == current_app.config.get('ADMIN_CLIENT_USER_NAME'):
        g.service_id = current_app.config.get('ADMIN_CLIENT_USER_NAME')
        return handle_admin_key(auth_token, current_app.config.get('ADMIN_CLIENT_SECRET'))
    else:
        raise AuthError('Unauthorized: admin authentication token required', 401)


def requires_auth():
    request_helper.check_proxy_header_before_request()

    auth_token = get_auth_token(request)
    issuer = __get_token_issuer(auth_token)  # ie the `iss` claim which should be a service ID

    try:
        service = dao_fetch_service_by_id_with_api_keys(issuer)
    except DataError:
        raise AuthError("Invalid token: service id is not the right data type", 403)
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

        g.service_id = api_key.service_id
        _request_ctx_stack.top.authenticated_service = service
        _request_ctx_stack.top.api_user = api_key
        current_app.logger.info('API authorised for service {} with api key {}, using issuer {}'.format(
            service.id,
            api_key.id,
            request.headers.get('User-Agent')
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


def handle_admin_key(auth_token, secret):
    try:
        decode_jwt_token(auth_token, secret)
    except TokenExpiredError:
        raise AuthError("Invalid token: expired, check that your system clock is accurate", 403)
    except TokenDecodeError:
        raise AuthError("Invalid token: could not decode your API token", 403)
