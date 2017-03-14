import uuid

from flask import jsonify, request
from werkzeug.exceptions import abort

from app import api_user
from app.dao import templates_dao
from app.schema_validation import validate
from app.v2.template import template_blueprint
from app.v2.template.template_schemas import get_template_by_id_request


@template_blueprint.route("/<template_id>", methods=['GET'])
@template_blueprint.route("/<template_id>/version/<version>", methods=['GET'])
def get_template_by_id(template_id, version=None):
    try:
        casted_id = uuid.UUID(template_id)

        _data = {}
        _data['id'] = template_id
        if version:
            _data['version'] = int(version)

        data = validate(_data, get_template_by_id_request)
    except ValueError or AttributeError:
        abort(404)

    template = templates_dao.dao_get_template_by_id_and_service_id(
        casted_id, api_user.service_id, data.get('version'))

    return jsonify(template.serialize()), 200
