from flask import Blueprint, jsonify, request

from app.dao.organisations_dao import (
    dao_create_organisation,
    dao_get_organisations,
    dao_get_organisation_by_id,
    dao_update_organisation
)
from app.errors import register_errors
from app.models import Organisation
from app.organisation.organisation_schema import post_create_organisation_schema, post_update_organisation_schema
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
def create_organisation():
    data = request.get_json()

    validate(data, post_create_organisation_schema)

    organisation = Organisation(**data)

    dao_create_organisation(organisation)
    return jsonify(data=organisation.serialize()), 201


@organisation_blueprint.route('/<uuid:organisation_id>', methods=['POST'])
def update_organisation(organisation_id):
    data = request.get_json()

    validate(data, post_update_organisation_schema)

    fetched_organisation = dao_get_organisation_by_id(organisation_id)
    dao_update_organisation(fetched_organisation, **data)

    return jsonify(data=fetched_organisation.serialize()), 200
