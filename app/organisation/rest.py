from flask import Blueprint, jsonify, request

from app.dao.organisations_dao import (
    dao_get_organisations,
    dao_get_organisation_by_id,
    dao_create_organisation
)
from app.errors import (
    InvalidRequest,
    register_errors
)
from app.models import Organisation
from app.organisation.organisation_schema import post_organisation_schema
from app.schema_validation import validate

organisation_blueprint = Blueprint('organisation', __name__)
register_errors(organisation_blueprint)


@organisation_blueprint.route('', methods=['GET'])
def get_organisations():
    organisations = [o.serialize() for o in dao_get_organisations()]
    return jsonify(organisations=organisations)


@organisation_blueprint.route('/<uuid:org_id>', methods=['GET'])
def get_organisation_by_id(org_id):
    organisation = dao_get_organisation_by_id(org_id)
    return jsonify(organisation=organisation.serialize())


@organisation_blueprint.route('', methods=['POST'])
def post_organisation():
    data = request.get_json()

    validate(data, post_organisation_schema)

    organisation = Organisation(**data)

    dao_create_organisation(organisation)
    return jsonify(data=organisation.serialize()), 201
