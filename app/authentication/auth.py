from flask import request, jsonify, _request_ctx_stack
from client.authentication import decode_jwt_token, get_token_issuer
from client.errors import TokenDecodeError, TokenRequestError, TokenExpiredError, TokenPayloadError
from app.dao.api_key_dao import get_unsigned_secrets


def authentication_response(message, code):
    return jsonify(
        error=message
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
    if api_client is None:
        authentication_response("Invalid credentials", 403)
    # If the api_client does not have any secrets return response saying that
    errors_resp = authentication_response("Invalid token: api client has no secrets", 403)
    for secret in api_client['secret']:
        try:
            decode_jwt_token(
                auth_token,
                secret,
                request.method,
                request.path,
                request.data.decode() if request.data else None
            )
            _request_ctx_stack.top.api_user = api_client
            return
        except TokenRequestError:
            errors_resp = authentication_response("Invalid token: request", 403)
        except TokenExpiredError:
            errors_resp = authentication_response("Invalid token: expired", 403)
        except TokenPayloadError:
            errors_resp = authentication_response("Invalid token: payload", 403)
        except TokenDecodeError:
            errors_resp = authentication_response("Invalid token: signature", 403)

    return errors_resp


def fetch_client(client):
    from flask import current_app
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
