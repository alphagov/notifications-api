from datetime import datetime

from flask import Blueprint
from flask import (
    jsonify,
    request
)
from sqlalchemy.orm.exc import NoResultFound

from app import email_safe
from app.dao.api_key_dao import (
    save_model_api_key,
    get_model_api_keys,
    get_unsigned_secret
)
from app.dao.services_dao import (
    dao_fetch_service_by_id_and_user,
    dao_fetch_service_by_id,
    dao_fetch_all_services,
    dao_create_service,
    dao_update_service,
    dao_fetch_all_services_by_user
)
from app.dao.users_dao import get_model_users
from app.models import ApiKey
from app.schemas import (
    services_schema,
    service_schema,
    api_keys_schema,
    users_schema)
from app.errors import register_errors

service = Blueprint('service', __name__)


register_errors(service)


@service.route('', methods=['GET'])
def get_services():
    user_id = request.args.get('user_id', None)
    if user_id:
        services = dao_fetch_all_services_by_user(user_id)
    else:
        services = dao_fetch_all_services()
    data, errors = services_schema.dump(services)
    return jsonify(data=data)


@service.route('/<service_id>', methods=['GET'])
def get_service_by_id(service_id):
    user_id = request.args.get('user_id', None)
    if user_id:
        fetched = dao_fetch_service_by_id_and_user(service_id, user_id)
    else:
        fetched = dao_fetch_service_by_id(service_id)
    if not fetched:
        message_with_user_id = 'and for user id: {}'.format(user_id) if user_id else ''
        return jsonify(result="error",
                       message="Service not found for service id: {0} {1}".format(service_id,
                                                                                  message_with_user_id)), 404
    data, errors = service_schema.dump(fetched)
    return jsonify(data=data)


@service.route('', methods=['POST'])
def create_service():
    data = request.get_json()
    if not data.get('user_id', None):
        return jsonify(result="error", message={'user_id': ['Missing data for required field.']}), 400

    user = get_model_users(data['user_id'])
    if not user:
        return jsonify(result="error", message={'user_id': ['not found']}), 400

    data.pop('user_id', None)
    if 'name' in data:
        data['email_from'] = email_safe(data.get('name', None))

    valid_service, errors = service_schema.load(request.get_json())

    if errors:
        return jsonify(result="error", message=errors), 400

    dao_create_service(valid_service, user)
    return jsonify(data=service_schema.dump(valid_service).data), 201


@service.route('/<service_id>', methods=['POST'])
def update_service(service_id):
    fetched_service = dao_fetch_service_by_id(service_id)
    if not fetched_service:
        return _service_not_found(service_id)

    current_data = dict(service_schema.dump(fetched_service).data.items())
    current_data.update(request.get_json())

    update_dict, errors = service_schema.load(current_data)
    if errors:
        return jsonify(result="error", message=errors), 400
    dao_update_service(update_dict)
    return jsonify(data=service_schema.dump(fetched_service).data), 200


@service.route('/<service_id>/api-key', methods=['POST'])
def renew_api_key(service_id=None):
    fetched_service = dao_fetch_service_by_id(service_id=service_id)
    if not fetched_service:
        return _service_not_found(service_id)

    # create a new one
    # TODO: what validation should be done here?
    secret_name = request.get_json()['name']
    key = ApiKey(service=fetched_service, name=secret_name)
    save_model_api_key(key)

    unsigned_api_key = get_unsigned_secret(key.id)
    return jsonify(data=unsigned_api_key), 201


@service.route('/<service_id>/api-key/revoke/<int:api_key_id>', methods=['POST'])
def revoke_api_key(service_id, api_key_id):
    service_api_key = get_model_api_keys(service_id=service_id, id=api_key_id)

    save_model_api_key(service_api_key, update_dict={'id': service_api_key.id, 'expiry_date': datetime.utcnow()})
    return jsonify(), 202


@service.route('/<service_id>/api-keys', methods=['GET'])
@service.route('/<service_id>/api-keys/<int:key_id>', methods=['GET'])
def get_api_keys(service_id, key_id=None):
    fetched_service = dao_fetch_service_by_id(service_id=service_id)
    if not fetched_service:
        return _service_not_found(service_id)
    try:
        if key_id:
            api_keys = [get_model_api_keys(service_id=service_id, id=key_id)]
        else:
            api_keys = get_model_api_keys(service_id=service_id)
    except NoResultFound:
        return jsonify(result="error", message="API key not found for id: {}".format(service_id)), 404

    return jsonify(apiKeys=api_keys_schema.dump(api_keys).data), 200


@service.route('/<service_id>/users', methods=['GET'])
def get_users_for_service(service_id):
    fetched = dao_fetch_service_by_id(service_id)
    if not fetched:
        return _service_not_found(service_id)
    if not fetched.users:
        return jsonify(data=[])

    result = users_schema.dump(fetched.users)
    return jsonify(data=result.data)


def _service_not_found(service_id):
    return jsonify(result='error', message='Service not found for id: {}'.format(service_id)), 404
