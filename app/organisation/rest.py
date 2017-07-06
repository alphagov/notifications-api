from flask import Blueprint, jsonify, request

from app.dao.organisations_dao import dao_get_organisations, dao_get_organisation_by_id, dao_create_organisation
from app.schemas import organisation_schema
from app.errors import (
    InvalidRequest,
    register_errors
)
from app.models import Organisation

organisation_blueprint = Blueprint('organisation', __name__)
register_errors(organisation_blueprint)


@organisation_blueprint.route('', methods=['GET'])
def get_organisations():
    data = organisation_schema.dump(dao_get_organisations(), many=True).data
    return jsonify(organisations=data)


@organisation_blueprint.route('/<uuid:org_id>', methods=['GET'])
def get_organisation_by_id(org_id):
    data = organisation_schema.dump(dao_get_organisation_by_id(org_id)).data
    return jsonify(organisation=data)


@organisation_blueprint.route('', methods=['POST'])
def post_organisation():
    data = request.get_json()
    if not data.get('logo', None):
        errors = {'logo': ['Missing data for required field.']}
        raise InvalidRequest(errors, status_code=400)

    # validate json with marshmallow
    organisation_schema.load(request.get_json())

    # unpack valid json into service object
    valid_organisation = Organisation.from_json(data)

    dao_create_organisation(valid_organisation)
    return jsonify(data=organisation_schema.dump(valid_organisation).data), 201
