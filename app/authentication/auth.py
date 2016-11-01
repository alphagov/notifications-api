from flask import request, _request_ctx_stack, current_app
from sqlalchemy.exc import DataError
from sqlalchemy.orm.exc import NoResultFound

from notifications_python_client.authentication import decode_jwt_token, get_token_issuer
from notifications_python_client.errors import TokenDecodeError, TokenExpiredError

from app.dao.api_key_dao import get_model_api_keys
from app.dao.services_dao import dao_fetch_service_by_id


class AuthError(Exception):
    def __init__(self, message, code):
        self.message = {"token": [message]}
        self.short_message = message
        self.code = code

    def to_dict_v2(self):
        return {'code': self.code,
                'message': self.short_message,
                'fields': self.message,
                'link': 'link to docs'}


def get_auth_token(req):
    auth_header = req.headers.get('Authorization', None)
    if not auth_header:
        raise AuthError('Unauthorized, authentication token must be provided', 401)

    auth_scheme = auth_header[:7]

    if auth_scheme != 'Bearer ':
        raise AuthError('Unauthorized, authentication bearer scheme must be used', 401)

    return auth_header[7:]


def requires_auth():
    auth_token = get_auth_token(request)
    try:
        client = get_token_issuer(auth_token)
    except TokenDecodeError:
        raise AuthError("Invalid token: signature", 403)

    if client == current_app.config.get('ADMIN_CLIENT_USER_NAME'):
        return handle_admin_key(auth_token, current_app.config.get('ADMIN_CLIENT_SECRET'))

    try:
        api_keys = get_model_api_keys(client)
    except DataError:
        raise AuthError("Invalid token: service id is not the right data type", 403)
    for api_key in api_keys:
        try:
            get_decode_errors(auth_token, api_key.unsigned_secret)
        except TokenDecodeError:
            continue

        if api_key.expiry_date:
            raise AuthError("Invalid token: API key revoked", 403)

        _request_ctx_stack.top.api_user = api_key
        return

    try:
        dao_fetch_service_by_id(client)
    except NoResultFound:
        raise AuthError("Invalid token: service not found", 403)

    if not api_keys:
        raise AuthError("Invalid token: service has no API keys", 403)
    else:
        raise AuthError("Invalid token: signature, api token is not valid", 403)


def handle_admin_key(auth_token, secret):
    try:
        get_decode_errors(auth_token, secret)
        return
    except TokenDecodeError:
        raise AuthError("Invalid token: signature", 403)


def get_decode_errors(auth_token, unsigned_secret):
    try:
        decode_jwt_token(auth_token, unsigned_secret)
    except TokenExpiredError:
        raise AuthError("Invalid token: expired", 403)
