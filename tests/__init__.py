import uuid
from flask import current_app
from notifications_python_client.authentication import create_jwt_token
from app.models import ApiKey, KEY_TYPE_NORMAL
from app.dao.api_key_dao import (get_unsigned_secrets, save_model_api_key)
from app.dao.services_dao import dao_fetch_service_by_id


def create_authorization_header(service_id=None):
    if service_id:
        client_id = str(service_id)
        secrets = get_unsigned_secrets(service_id)
        if secrets:
            secret = secrets[0]
        else:
            service = dao_fetch_service_by_id(service_id)
            data = {
                'service': service,
                'name': uuid.uuid4(),
                'created_by': service.created_by,
                'key_type': KEY_TYPE_NORMAL
            }
            api_key = ApiKey(**data)
            save_model_api_key(api_key)
            secret = get_unsigned_secrets(service_id)[0]

    else:
        client_id = current_app.config.get('ADMIN_CLIENT_USER_NAME')
        secret = current_app.config.get('ADMIN_CLIENT_SECRET')

    token = create_jwt_token(secret=secret, client_id=client_id)
    return 'Authorization', 'Bearer {}'.format(token)
