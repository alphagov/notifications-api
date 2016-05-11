from flask import Blueprint, jsonify, request

from app.schemas import provider_details_schema
from app.dao.provider_details_dao import (
    get_provider_details,
    get_provider_details_by_id,
    get_provider_details_by_id,
    dao_update_provider_details
)

provider_details = Blueprint('provider_details', __name__)


@provider_details.route('', methods=['GET'])
def get_providers():
    data, errors = provider_details_schema.dump(get_provider_details(), many=True)
    return jsonify(provider_details=data)


@provider_details.route('/<uuid:provider_details_id>', methods=['GET'])
def get_provider_by_id(provider_details_id):
    data, errors = provider_details_schema.dump(get_provider_details_by_id(provider_details_id))
    return jsonify(provider_details=data)


@provider_details.route('/<uuid:provider_details_id>', methods=['POST'])
def update_provider_details(provider_details_id):
    fetched_provider_details = get_provider_details_by_id(provider_details_id)

    current_data = dict(provider_details_schema.dump(fetched_provider_details).data.items())
    current_data.update(request.get_json())
    update_dict, errors = provider_details_schema.load(current_data)
    if errors:
        return jsonify(result="error", message=errors), 400

    if "identifier" in request.get_json().keys():
        return jsonify(message={
            "identifier": ["Not permitted to be updated"]
        }, result='error'), 400

    dao_update_provider_details(update_dict)
    return jsonify(provider_details=provider_details_schema.dump(fetched_provider_details).data), 200
