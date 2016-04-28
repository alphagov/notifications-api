from datetime import datetime

from flask import Blueprint
from flask import (
    jsonify,
    request
)
from sqlalchemy.orm.exc import NoResultFound

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
    dao_fetch_all_services_by_user,
    dao_add_user_to_service,
    dao_remove_user_from_service
)

from app.dao.users_dao import get_model_users
from app.models import ApiKey
from app.schemas import (
    service_schema,
    api_key_schema,
    user_schema
)

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
    data, errors = service_schema.dump(services, many=True)
    return jsonify(data=data)


@service.route('/<uuid:service_id>', methods=['GET'])
def get_service_by_id(service_id):
    user_id = request.args.get('user_id', None)
    if user_id:
        fetched = dao_fetch_service_by_id_and_user(service_id, user_id)
    else:
        fetched = dao_fetch_service_by_id(service_id)

    data, errors = service_schema.dump(fetched)
    return jsonify(data=data)


@service.route('', methods=['POST'])
def create_service():
    data = request.get_json()
    if not data.get('user_id', None):
        return jsonify(result="error", message={'user_id': ['Missing data for required field.']}), 400

    user = get_model_users(data['user_id'])

    data.pop('user_id', None)
    valid_service, errors = service_schema.load(request.get_json())

    if errors:
        return jsonify(result="error", message=errors), 400

    dao_create_service(valid_service, user)
    return jsonify(data=service_schema.dump(valid_service).data), 201


@service.route('/<uuid:service_id>', methods=['POST'])
def update_service(service_id):
    fetched_service = dao_fetch_service_by_id(service_id)

    current_data = dict(service_schema.dump(fetched_service).data.items())
    current_data.update(request.get_json())
    update_dict, errors = service_schema.load(current_data)
    if errors:
        return jsonify(result="error", message=errors), 400
    dao_update_service(update_dict)
    return jsonify(data=service_schema.dump(fetched_service).data), 200


@service.route('/<uuid:service_id>/api-key', methods=['POST'])
def renew_api_key(service_id=None):
    fetched_service = dao_fetch_service_by_id(service_id=service_id)

    valid_api_key, errors = api_key_schema.load(request.get_json())
    if errors:
        return jsonify(result="error", message=errors), 400
    valid_api_key.service = fetched_service

    save_model_api_key(valid_api_key)

    unsigned_api_key = get_unsigned_secret(valid_api_key.id)
    return jsonify(data=unsigned_api_key), 201


@service.route('/<uuid:service_id>/api-key/revoke/<uuid:api_key_id>', methods=['POST'])
def revoke_api_key(service_id, api_key_id):
    service_api_key = get_model_api_keys(service_id=service_id, id=api_key_id)
    save_model_api_key(service_api_key, update_dict={'expiry_date': datetime.utcnow()})
    return jsonify(), 202


@service.route('/<uuid:service_id>/api-keys', methods=['GET'])
@service.route('/<uuid:service_id>/api-keys/<uuid:key_id>', methods=['GET'])
def get_api_keys(service_id, key_id=None):
    dao_fetch_service_by_id(service_id=service_id)

    try:
        if key_id:
            api_keys = [get_model_api_keys(service_id=service_id, id=key_id)]
        else:
            api_keys = get_model_api_keys(service_id=service_id)
    except NoResultFound:
        return jsonify(result="error", message="API key not found for id: {}".format(service_id)), 404

    return jsonify(apiKeys=api_key_schema.dump(api_keys, many=True).data), 200


@service.route('/<uuid:service_id>/users', methods=['GET'])
def get_users_for_service(service_id):
    fetched = dao_fetch_service_by_id(service_id)

    result = user_schema.dump(fetched.users, many=True)
    return jsonify(data=result.data)


@service.route('/<uuid:service_id>/users/<user_id>', methods=['POST'])
def add_user_to_service(service_id, user_id):
    service = dao_fetch_service_by_id(service_id)
    user = get_model_users(user_id=user_id)

    if user in service.users:
        return jsonify(result='error',
                       message='User id: {} already part of service id: {}'.format(user_id, service_id)), 400

    permissions_json = request.get_json().get('permissions', [])
    permissions = _process_permissions(user, service, permissions_json)
    dao_add_user_to_service(service, user, permissions)

    data, errors = service_schema.dump(service)
    return jsonify(data=data), 201


@service.route('/<uuid:service_id>/users/<user_id>', methods=['DELETE'])
def remove_user_from_service(service_id, user_id):
    service = dao_fetch_service_by_id(service_id)
    user = get_model_users(user_id=user_id)
    if user not in service.users:
        return jsonify(
            result='error',
            message='User not found'), 404
    elif len(service.users) == 1:
        return jsonify(
            result='error',
            message='You cannot remove the only user for a service'), 400
    dao_remove_user_from_service(service, user)
    return jsonify({}), 204


def _process_permissions(user, service, permission_groups):
    from app.permissions_utils import get_permissions_by_group
    permissions = get_permissions_by_group(permission_groups)
    for permission in permissions:
        permission.user = user
        permission.service = service
    return permissions


# This is placeholder get method until more thought
# goes into how we want to fetch and view various items in history
# tables. This is so product owner can pass stories as done
@service.route('/<uuid:service_id>/history', methods=['GET'])
def get_service_history(service_id):
    from app.models import (Service, ApiKey, Template, Event)
    from app.schemas import (
        service_history_schema,
        api_key_history_schema,
        template_history_schema,
        event_schema
    )

    service_history = Service.get_history_model().query.filter_by(id=service_id).all()
    service_data, errors = service_history_schema.dump(service_history, many=True)
    if errors:
        return jsonify(result="error", message=errors), 400

    api_key_history = ApiKey.get_history_model().query.filter_by(service_id=service_id).all()

    api_keys_data, errors = api_key_history_schema.dump(api_key_history, many=True)
    if errors:
        return jsonify(result="error", message=errors), 400

    template_history = Template.get_history_model().query.filter_by(service_id=service_id).all()
    template_data, errors = template_history_schema.dump(template_history, many=True)

    events = Event.query.all()
    events_data, errors = event_schema.dump(events, many=True)

    data = {
        'service_history': service_data,
        'api_key_history': api_keys_data,
        'template_history': template_data,
        'events': events_data}

    return jsonify(data=data)
