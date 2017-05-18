from flask import jsonify

from app import authenticated_service
from app.dao import templates_dao
from app.schema_validation import validate
from app.v2.template import v2_template_blueprint
from app.v2.template.template_schemas import get_template_by_id_request


@v2_template_blueprint.route("/<template_id>", methods=['GET'])
@v2_template_blueprint.route("/<template_id>/version/<int:version>", methods=['GET'])
def get_template_by_id(template_id, version=None):
    _data = {'id': template_id}
    if version:
        _data['version'] = version

    data = validate(_data, get_template_by_id_request)

    template = templates_dao.dao_get_template_by_id_and_service_id(
        template_id, authenticated_service.id, data.get('version'))

    return jsonify(template.serialize()), 200
