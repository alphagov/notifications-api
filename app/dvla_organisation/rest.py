from flask import Blueprint, jsonify

from app.dao.dvla_organisation_dao import dao_get_dvla_organisations
from app.errors import register_errors

dvla_organisation_blueprint = Blueprint('dvla_organisation', __name__)
register_errors(dvla_organisation_blueprint)


@dvla_organisation_blueprint.route('', methods=['GET'])
def get_dvla_organisations():
    return jsonify({
        org.id: org.name for org in dao_get_dvla_organisations()
    })
