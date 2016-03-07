from flask import (
    Blueprint,
    jsonify,
    request,
    current_app
)
import bleach
from sqlalchemy.exc import IntegrityError

from app.dao.templates_dao import (
    dao_update_template,
    dao_create_template,
    dao_get_template_by_id_and_service_id,
    dao_get_all_templates_for_service
)
from app.dao.services_dao import (
    dao_fetch_service_by_id
)
from app.schemas import template_schema

template = Blueprint('template', __name__, url_prefix='/service/<service_id>/template')

from app.errors import register_errors

register_errors(template)


@template.route('', methods=['POST'])
def create_template(service_id):
    fetched_service = dao_fetch_service_by_id(service_id=service_id)
    if not fetched_service:
        return jsonify(result="error", message="Service not found"), 404

    new_template, errors = template_schema.load(request.get_json())
    if errors:
        return jsonify(result="error", message=errors), 400
    new_template.service = fetched_service
    new_template.content = _strip_html(new_template.content)
    try:
        dao_create_template(new_template)
    except IntegrityError as ex:
        current_app.logger.debug(ex)
        message = "Failed to create template"
        if "templates_subject_key" in str(ex):
            message = 'Duplicate template subject'
            return jsonify(result="error", message=[{'subject': message}]), 400
        return jsonify(result="error", message=message), 500

    return jsonify(data=template_schema.dump(new_template).data), 201


@template.route('/<int:template_id>', methods=['POST'])
def update_template(service_id, template_id):
    fetched_template = dao_get_template_by_id_and_service_id(template_id=template_id, service_id=service_id)
    if not fetched_template:
        return jsonify(result="error", message="Template not found"), 404

    current_data = dict(template_schema.dump(fetched_template).data.items())
    current_data.update(request.get_json())
    current_data['content'] = _strip_html(current_data['content'])

    update_dict, errors = template_schema.load(current_data)
    if errors:
        return jsonify(result="error", message=errors), 400

    dao_update_template(update_dict)
    return jsonify(data=template_schema.dump(update_dict).data), 200


@template.route('', methods=['GET'])
def get_all_templates_for_service(service_id):
    templates = dao_get_all_templates_for_service(service_id=service_id)
    data, errors = template_schema.dump(templates, many=True)
    return jsonify(data=data)


@template.route('/<int:template_id>', methods=['GET'])
def get_template_by_id_and_service_id(service_id, template_id):
    fetched_template = dao_get_template_by_id_and_service_id(template_id=template_id, service_id=service_id)
    if fetched_template:
        data, errors = template_schema.dump(fetched_template)
        return jsonify(data=data)
    else:
        return jsonify(result="error", message="Template not found"), 404


def _strip_html(content):
    return bleach.clean(content, tags=[], strip=True)
