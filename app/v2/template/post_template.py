from flask import jsonify, request

from app import authenticated_service
from app.dao import templates_dao
from app.schema_validation import validate
from app.utils import get_template_instance
from app.v2.errors import BadRequestError
from app.v2.template import v2_template_blueprint
from app.v2.template.template_schemas import post_template_preview_request, create_post_template_preview_response


@v2_template_blueprint.route("/<template_id>/preview", methods=['POST'])
def post_template_preview(template_id):
    _data = request.get_json()
    if _data is None:
        _data = {}

    _data['id'] = template_id

    data = validate(_data, post_template_preview_request)

    template = templates_dao.dao_get_template_by_id_and_service_id(
        template_id, authenticated_service.id)

    template_object = get_template_instance(
        template.__dict__, values=data.get('personalisation'))

    check_placeholders(template_object)

    resp = create_post_template_preview_response(template=template,
                                                 template_object=template_object)

    return jsonify(resp), 200


def check_placeholders(template_object):
    if template_object.missing_data:
        message = 'Missing personalisation: {}'.format(", ".join(template_object.missing_data))
        raise BadRequestError(message=message, fields=[{'template': message}])
