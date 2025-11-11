import datetime

from flask import Blueprint, jsonify, request

from app.constants import EMAIL_TYPE
from app.dao.services_dao import dao_fetch_service_by_id
from app.dao.template_email_files_dao import (
    dao_create_template_email_files,
)
from app.dao.templates_dao import dao_get_template_by_id_and_service_id
from app.errors import InvalidRequest
from app.models import TemplateEmailFile
from app.schema_validation import validate
from app.schemas import template_email_files_schema
from app.template_email_files.template_email_files_schemas import (
    post_create_template_email_files_schema,
)

template_email_files_blueprint = Blueprint(
    "template_email_files", __name__, url_prefix="/service/<uuid:service_id>/<uuid:template_id>/template_email_files"
)

@template_email_files_blueprint.route("", methods=["POST"])
def create_template_email_files(service_id, template_id):
    fetched_service = dao_fetch_service_by_id(service_id=service_id)
    template_email_files_json = validate(request.get_json(), post_create_template_email_files_schema)
    fetched_template = dao_get_template_by_id_and_service_id(template_id, service_id)
    if fetched_template.template_type != EMAIL_TYPE:
        raise InvalidRequest(message="cannot create an email for non-email type", status_code=400)
    if not fetched_service.has_permission(EMAIL_TYPE):
        raise InvalidRequest(message="can't create email type", status_code=400)
    template_email_file = TemplateEmailFile.from_json(template_email_files_json)
    dao_create_template_email_files(template_email_file)
    return jsonify(data=template_email_files_schema.dump(template_email_file)), 201

