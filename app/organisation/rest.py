from flask import Blueprint, jsonify

from app.dao.organisation_dao import dao_get_organisations, dao_get_organisation_by_id
from app.schemas import organisation_schema
from app.errors import register_errors

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
