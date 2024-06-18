import uuid

from flask import current_app
from notifications_python_client.authentication import create_jwt_token

from app.constants import KEY_TYPE_NORMAL
from app.dao.api_key_dao import save_model_api_key
from app.dao.services_dao import dao_fetch_service_by_id
from app.models import ApiKey


def create_service_authorization_header(service_id, key_type=KEY_TYPE_NORMAL):
    client_id = str(service_id)
    secrets = ApiKey.query.filter_by(service_id=service_id, key_type=key_type).all()

    if secrets:
        secret = secrets[0].secret
    else:
        service = dao_fetch_service_by_id(service_id)
        data = {"service": service, "name": uuid.uuid4(), "created_by": service.created_by, "key_type": key_type}
        api_key = ApiKey(**data)
        save_model_api_key(api_key)
        secret = api_key.secret

    token = create_jwt_token(secret=secret, client_id=client_id)
    return "Authorization", f"Bearer {token}"


def create_admin_authorization_header():
    client_id = current_app.config["ADMIN_CLIENT_ID"]
    return create_internal_authorization_header(client_id)


def create_functional_tests_authorization_header():
    client_id = current_app.config["FUNCTIONAL_TESTS_CLIENT_ID"]
    return create_internal_authorization_header(client_id)


def create_internal_authorization_header(client_id):
    secret = current_app.config["INTERNAL_CLIENT_API_KEYS"][client_id][0]
    token = create_jwt_token(secret=secret, client_id=client_id)
    return "Authorization", f"Bearer {token}"


def unwrap_function(fn):
    """
    Given a function, returns its undecorated original.
    """
    while hasattr(fn, "__wrapped__"):
        fn = fn.__wrapped__
    return fn
