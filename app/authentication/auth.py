from flask import request, jsonify, _request_ctx_stack
from client.authentication import decode_jwt_token, get_token_issuer
from client.errors import TokenDecodeError, TokenRequestError, TokenExpiredError, TokenPayloadError

from app.dao.api_key_dao import get_unsigned_secret


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

    try:
        auth_token = auth_header[7:]
        api_client = fetch_client(get_token_issuer(auth_token))
        if api_client is None:
            authentication_response("Invalid credentials", 403)

        decode_jwt_token(
            auth_token,
            api_client['secret'],
            request.method,
            request.path,
            request.data.decode() if request.data else None
        )
        _request_ctx_stack.top.api_user = api_client
    except TokenRequestError:
        return authentication_response("Invalid token: request", 403)
    except TokenExpiredError:
        return authentication_response("Invalid token: expired", 403)
    except TokenPayloadError:
        return authentication_response("Invalid token: payload", 403)
    except TokenDecodeError:
        return authentication_response("Invalid token: signature", 403)


def fetch_client(client):
    return {
        "client": client,
        "secret": get_unsigned_secret(client)
    }
