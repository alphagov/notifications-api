import json

from flask import jsonify, request, current_app, url_for
from jsonschema.exceptions import ValidationError

from app import api_user
from app.dao import templates_dao
from app.schema_validation import validate
from app.v2.templates import v2_templates_blueprint
from app.v2.templates.templates_schemas import get_all_template_request


@v2_templates_blueprint.route("/", methods=['GET'])
def get_templates():
    _data = request.args.to_dict()

    data = validate(_data, get_all_template_request)

    templates = templates_dao.dao_get_all_templates_for_service(
        api_user.service_id,
        older_than=data.get('older_than'),
        page_size=current_app.config.get('API_PAGE_SIZE'))

    def _build_links(templates):
        _links = {
            'current': url_for(".get_templates", _external=True, **data),
        }

        if len(templates):
            next_query_params = dict(data, older_than=templates[-1].id)
            _links['next'] = url_for(".get_templates", _external=True, **next_query_params)

        return _links

    return jsonify(
        templates=[template.serialize() for template in templates],
        links=_build_links(templates)
    ), 200
