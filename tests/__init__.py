from flask import current_app
from client.authentication import create_jwt_token

from app.dao.api_key_dao import get_unsigned_secrets


def create_authorization_header(path, method, request_body=None, service_id=None):
    if service_id:
        client_id = str(service_id)
        secret = get_unsigned_secrets(service_id)[0]
    else:
        client_id = current_app.config.get('ADMIN_CLIENT_USER_NAME')
        secret = current_app.config.get('ADMIN_CLIENT_SECRET')

    if request_body:
        token = create_jwt_token(
            request_method=method,
            request_path=path,
            secret=secret,
            client_id=client_id,
            request_body=request_body)

    else:
        token = create_jwt_token(request_method=method,
                                 request_path=path,
                                 secret=secret,
                                 client_id=client_id)

    return 'Authorization', 'Bearer {}'.format(token)
