from flask import (
    Blueprint,
    jsonify,
    request,
    current_app
)

from app.dao.templates_dao import (
    dao_update_template,
    dao_create_template,
    dao_redact_template,
    dao_get_template_by_id_and_service_id,
    dao_get_all_templates_for_service,
    dao_get_template_versions
)
from notifications_utils.template import SMSMessageTemplate
from app.dao.services_dao import dao_fetch_service_by_id
from app.models import SMS_TYPE
from app.schemas import (template_schema, template_history_schema)

template_blueprint = Blueprint('template', __name__, url_prefix='/service/<uuid:service_id>/template')

from app.errors import (
    register_errors,
    InvalidRequest
)
from app.utils import get_template_instance

register_errors(template_blueprint)


def _content_count_greater_than_limit(content, template_type):
    if template_type != SMS_TYPE:
        return False
    template = SMSMessageTemplate({'content': content, 'template_type': template_type})
    return template.content_count > current_app.config.get('SMS_CHAR_COUNT_LIMIT')


@template_blueprint.route('', methods=['POST'])
def create_template(service_id):
    fetched_service = dao_fetch_service_by_id(service_id=service_id)
    new_template = template_schema.load(request.get_json()).data
    new_template.service = fetched_service
    over_limit = _content_count_greater_than_limit(new_template.content, new_template.template_type)
    if over_limit:
        char_count_limit = current_app.config.get('SMS_CHAR_COUNT_LIMIT')
        message = 'Content has a character count greater than the limit of {}'.format(char_count_limit)
        errors = {'content': [message]}
        raise InvalidRequest(errors, status_code=400)

    dao_create_template(new_template)
    return jsonify(data=template_schema.dump(new_template).data), 201


@template_blueprint.route('/<uuid:template_id>', methods=['POST'])
def update_template(service_id, template_id):
    fetched_template = dao_get_template_by_id_and_service_id(template_id=template_id, service_id=service_id)

    data = request.get_json()

    # if redacting, don't update anything else
    if data.get('redact_personalisation') is True:
        return redact_template(fetched_template, data)

    current_data = dict(template_schema.dump(fetched_template).data.items())
    updated_template = dict(template_schema.dump(fetched_template).data.items())
    updated_template.update(data)
    # Check if there is a change to make.
    if _template_has_not_changed(current_data, updated_template):
        return jsonify(data=updated_template), 200

    update_dict = template_schema.load(updated_template).data
    over_limit = _content_count_greater_than_limit(updated_template['content'], fetched_template.template_type)
    if over_limit:
        char_count_limit = current_app.config.get('SMS_CHAR_COUNT_LIMIT')
        message = 'Content has a character count greater than the limit of {}'.format(char_count_limit)
        errors = {'content': [message]}
        raise InvalidRequest(errors, status_code=400)
    dao_update_template(update_dict)
    return jsonify(data=template_schema.dump(update_dict).data), 200


@template_blueprint.route('', methods=['GET'])
def get_all_templates_for_service(service_id):
    templates = dao_get_all_templates_for_service(service_id=service_id)
    data = template_schema.dump(templates, many=True).data
    return jsonify(data=data)


@template_blueprint.route('/<uuid:template_id>', methods=['GET'])
def get_template_by_id_and_service_id(service_id, template_id):
    fetched_template = dao_get_template_by_id_and_service_id(template_id=template_id, service_id=service_id)
    data = template_schema.dump(fetched_template).data
    return jsonify(data=data)


@template_blueprint.route('/<uuid:template_id>/preview', methods=['GET'])
def preview_template_by_id_and_service_id(service_id, template_id):
    fetched_template = dao_get_template_by_id_and_service_id(template_id=template_id, service_id=service_id)
    data = template_schema.dump(fetched_template).data

    template_object = get_template_instance(data, values=request.args.to_dict())

    if template_object.missing_data:
        raise InvalidRequest(
            {'template': [
                'Missing personalisation: {}'.format(", ".join(template_object.missing_data))
            ]}, status_code=400
        )

    data['subject'], data['content'] = template_object.subject, str(template_object)

    return jsonify(data)


@template_blueprint.route('/<uuid:template_id>/version/<int:version>')
def get_template_version(service_id, template_id, version):
    data = template_history_schema.dump(
        dao_get_template_by_id_and_service_id(
            template_id=template_id,
            service_id=service_id,
            version=version
        )
    ).data
    return jsonify(data=data)


@template_blueprint.route('/<uuid:template_id>/versions')
def get_template_versions(service_id, template_id):
    data = template_history_schema.dump(
        dao_get_template_versions(service_id=service_id, template_id=template_id),
        many=True
    ).data
    return jsonify(data=data)


def _template_has_not_changed(current_data, updated_template):
    return all(
        current_data[key] == updated_template[key]
        for key in ('name', 'content', 'subject', 'archived', 'process_type')
    )


def redact_template(template, data):
    # we also don't need to check what was passed in redact_personalisation - its presence in the dict is enough.
    if 'updated_by_id' not in data:
        message = 'Field is required'
        errors = {'updated_by_id': [message]}
        raise InvalidRequest(errors, status_code=400)

    # if it's already redacted, then just return 200 straight away.
    if not template.redact_personalisation:
        dao_redact_template(template, data['updated_by_id'])
    return 'null', 200
