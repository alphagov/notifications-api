from flask import Blueprint, jsonify, request

from app.schemas import provider_details_schema, provider_details_history_schema
from app.dao.provider_details_dao import (
    get_provider_details,
    get_provider_details_by_id,
    dao_update_provider_details,
    dao_get_provider_versions
)
from app.dao.users_dao import get_user_by_id
from app.errors import (
    register_errors,
    InvalidRequest
)

provider_details = Blueprint('provider_details', __name__)
register_errors(provider_details)


@provider_details.route('', methods=['GET'])
def get_providers():
    data = provider_details_schema.dump(get_provider_details(), many=True).data
    return jsonify(provider_details=data)


@provider_details.route('/<uuid:provider_details_id>', methods=['GET'])
def get_provider_by_id(provider_details_id):
    data = provider_details_schema.dump(get_provider_details_by_id(provider_details_id)).data
    return jsonify(provider_details=data)


@provider_details.route('/<uuid:provider_details_id>/versions', methods=['GET'])
def get_provider_versions(provider_details_id):
    versions = dao_get_provider_versions(provider_details_id)
    data = provider_details_history_schema.dump(
        versions,
        many=True
    ).data
    return jsonify(data=data)


@provider_details.route('/<uuid:provider_details_id>', methods=['POST'])
def update_provider_details(provider_details_id):
    valid_keys = {'priority', 'created_by', 'active'}
    invalid_keys = request.get_json().keys() - valid_keys

    if invalid_keys:
        message = "Not permitted to be updated"
        errors = {key: [message] for key in invalid_keys}
        raise InvalidRequest(errors, status_code=400)

    provider = get_provider_details_by_id(provider_details_id)
    req_json = request.get_json()

    # Handle created_by differently due to how history entry is created
    if 'created_by' in req_json:
        user = get_user_by_id(req_json['created_by'])
        provider.created_by_id = user.id
        req_json.pop('created_by')

    for key in req_json:
        setattr(provider, key, req_json[key])
    dao_update_provider_details(provider)

    return jsonify(provider_details=provider_details_schema.dump(provider).data), 200
