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
    dao_get_all_templates_for_service,
    dao_get_template_versions
)
from notifications_utils.template import Template
from app.dao.services_dao import dao_fetch_service_by_id
from app.schemas import (template_schema, template_history_schema)

template = Blueprint('template', __name__, url_prefix='/service/<uuid:service_id>/template')

from app.errors import register_errors

register_errors(template)


def _content_count_greater_than_limit(content, template_type):
    template = Template({'content': content, 'template_type': template_type})
    if template_type == 'sms' and \
       template.content_count > current_app.config.get('SMS_CHAR_COUNT_LIMIT'):
        return True, jsonify(
            result="error",
            message={'content': ['Content has a character count greater than the limit of {}'.format(
                current_app.config.get('SMS_CHAR_COUNT_LIMIT'))]}
        )
    return False, ''


@template.route('', methods=['POST'])
def create_template(service_id):
    fetched_service = dao_fetch_service_by_id(service_id=service_id)
    new_template, errors = template_schema.load(request.get_json())
    if errors:
        return jsonify(result="error", message=errors), 400
    new_template.service = fetched_service
    new_template.content = _strip_html(new_template.content)
    over_limit, json_resp = _content_count_greater_than_limit(
        new_template.content,
        new_template.template_type)
    if over_limit:
        return json_resp, 400
    try:
        dao_create_template(new_template)
    except IntegrityError as ex:
        current_app.logger.debug(ex)
        message = "Failed to create template"
        if "templates_subject_key" in str(ex):
            message = 'Duplicate template subject'
            return jsonify(result="error", message={'subject': [message]}), 400
        return jsonify(result="error", message=message), 500

    return jsonify(data=template_schema.dump(new_template).data), 201


@template.route('/<uuid:template_id>', methods=['POST'])
def update_template(service_id, template_id):
    fetched_template = dao_get_template_by_id_and_service_id(template_id=template_id, service_id=service_id)

    current_data = dict(template_schema.dump(fetched_template).data.items())
    current_data.update(request.get_json())
    current_data['content'] = _strip_html(current_data['content'])

    update_dict, errors = template_schema.load(current_data)
    if errors:
        return jsonify(result="error", message=errors), 400
    over_limit, json_resp = _content_count_greater_than_limit(
        current_data['content'],
        fetched_template.template_type)
    if over_limit:
        return json_resp, 400
    dao_update_template(update_dict)
    return jsonify(data=template_schema.dump(update_dict).data), 200


@template.route('', methods=['GET'])
def get_all_templates_for_service(service_id):
    templates = dao_get_all_templates_for_service(service_id=service_id)
    data, errors = template_schema.dump(templates, many=True)
    return jsonify(data=data)


@template.route('/<uuid:template_id>', methods=['GET'])
def get_template_by_id_and_service_id(service_id, template_id):
    fetched_template = dao_get_template_by_id_and_service_id(template_id=template_id, service_id=service_id)
    data, errors = template_schema.dump(fetched_template)
    return jsonify(data=data)


@template.route('/<uuid:template_id>/version/<int:version>')
def get_template_version(service_id, template_id, version):
    fetched_template = dao_get_template_by_id_and_service_id(
        template_id=template_id,
        service_id=service_id,
        version=version
    )
    data, errors = template_history_schema.dump(fetched_template)
    if errors:
        return json_resp(result='error', message=errors), 400
    return jsonify(data=data)


@template.route('/<uuid:template_id>/version')
def get_template_versions(service_id, template_id):
    fetched_templates = dao_get_template_versions(service_id, template_id)
    data, errors = template_history_schema.dump(fetched_templates, many=True)
    if errors:
        return json_resp(result='error', message=errors), 400
    return jsonify(data=data)


def _strip_html(content):
    return bleach.clean(content, tags=[], strip=True)
