from flask import Blueprint, jsonify, request

from app.schemas import provider_details_schema

from app.dao.provider_details_dao import (
    get_provider_details,
    get_provider_details_by_id,
    dao_update_provider_details
)

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


@provider_details.route('/<uuid:provider_details_id>', methods=['POST'])
def update_provider_details(provider_details_id):
    fetched_provider_details = get_provider_details_by_id(provider_details_id)

    current_data = dict(provider_details_schema.dump(fetched_provider_details).data.items())
    current_data.update(request.get_json())
    update_dict = provider_details_schema.load(current_data).data

    invalid_keys = {'identifier', 'version', 'updated_at'} & set(key for key in request.get_json().keys())
    if invalid_keys:
        message = "Not permitted to be updated"
        errors = {key: [message] for key in invalid_keys}
        raise InvalidRequest(errors, status_code=400)

    dao_update_provider_details(update_dict)
    return jsonify(provider_details=provider_details_schema.dump(fetched_provider_details).data), 200
