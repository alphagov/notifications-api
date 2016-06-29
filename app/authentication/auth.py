from flask import request, jsonify, _request_ctx_stack, current_app
from notifications_python_client.authentication import decode_jwt_token, get_token_issuer
from notifications_python_client.errors import TokenDecodeError, TokenExpiredError

from app.dao.api_key_dao import get_model_api_keys


def authentication_response(message, code):
    return jsonify(result='error',
                   message={"token": [message]}
                   ), code


def requires_auth():
    auth_header = request.headers.get('Authorization', None)
    if not auth_header:
        return authentication_response('Unauthorized, authentication token must be provided', 401)

    auth_scheme = auth_header[:7]

    if auth_scheme != 'Bearer ':
        return authentication_response('Unauthorized, authentication bearer scheme must be used', 401)

    auth_token = auth_header[7:]
    try:
        client = get_token_issuer(auth_token)
    except TokenDecodeError:
        return authentication_response("Invalid token: signature", 403)

    if client == current_app.config.get('ADMIN_CLIENT_USER_NAME'):
        errors_resp = get_decode_errors(auth_token, current_app.config.get('ADMIN_CLIENT_SECRET'), expiry_date=None)
        return errors_resp

    secret_keys = get_model_api_keys(client)
    for api_key in secret_keys:
        errors_resp = get_decode_errors(auth_token, api_key.unsigned_secret, api_key.expiry_date)
        if not errors_resp:
            if api_key.expiry_date:
                return authentication_response("Invalid token: revoked", 403)
            else:
                _request_ctx_stack.top.api_user = api_key
                return

    if not secret_keys:
        errors_resp = authentication_response("Invalid token: no api keys for service", 403)
    current_app.logger.info(errors_resp)
    return errors_resp


def get_decode_errors(auth_token, unsigned_secret, expiry_date=None):
    try:
        decode_jwt_token(auth_token, unsigned_secret)
    except TokenExpiredError:
        return authentication_response("Invalid token: expired", 403)
    except TokenDecodeError:
        return authentication_response("Invalid token: signature", 403)
    else:
        return None
