from flask import request, jsonify, _request_ctx_stack, current_app
from notifications_python_client.authentication import decode_jwt_token, get_token_issuer
from notifications_python_client.errors import TokenDecodeError, TokenExpiredError
from werkzeug.exceptions import abort
from app.dao.api_key_dao import get_unsigned_secrets
from app import api_user
from functools import wraps


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
        api_client = fetch_client(get_token_issuer(auth_token))
    except TokenDecodeError:
        return authentication_response("Invalid token: signature", 403)

    for secret in api_client['secret']:
        try:
            decode_jwt_token(
                auth_token,
                secret
            )
            _request_ctx_stack.top.api_user = api_client
            return
        except TokenExpiredError:
            errors_resp = authentication_response("Invalid token: expired", 403)
        except TokenDecodeError:
            errors_resp = authentication_response("Invalid token: signature", 403)

    if not api_client['secret']:
        errors_resp = authentication_response("Invalid token: no api keys for service", 403)
    current_app.logger.info(errors_resp)
    return errors_resp


def fetch_client(client):
    if client == current_app.config.get('ADMIN_CLIENT_USER_NAME'):
        return {
            "client": client,
            "secret": [current_app.config.get('ADMIN_CLIENT_SECRET')]
        }
    else:
        return {
            "client": client,
            "secret": get_unsigned_secrets(client)
        }
