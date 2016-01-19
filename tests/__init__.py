from client.authentication import create_jwt_token

from app.dao.api_key_dao import get_unsigned_secret


def create_authorization_header(service_id, path, method, request_body=None):
    if request_body:
        token = create_jwt_token(
            request_method=method,
            request_path=path,
            secret=get_unsigned_secret(service_id),
            client_id=service_id,
            request_body=request_body)

    else:
        token = create_jwt_token(request_method=method,
                                 request_path=path,
                                 secret=get_unsigned_secret(service_id),
                                 client_id=service_id)

    return 'Authorization', 'Bearer {}'.format(token)
