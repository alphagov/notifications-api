import datetime

from flask import Blueprint, jsonify, request
from notifications_utils.insensitive_dict import InsensitiveSet

from app.constants import EMAIL_TYPE
from app.dao.services_dao import dao_fetch_service_by_id
from app.dao.template_email_files_dao import (
    dao_create_pending_template_email_file,
    dao_create_template_email_file,
    dao_get_template_email_file_by_id,
    dao_get_template_email_files_by_template_id,
    dao_make_pending_template_email_file_live,
    dao_update_pending_template_email_file,
    dao_update_template_email_file,
)
from app.dao.templates_dao import dao_get_template_by_id_and_service_id
from app.errors import InvalidRequest, register_errors
from app.models import TemplateEmailFile
from app.schema_validation import validate
from app.schemas import template_email_files_schema
from app.template_email_files.template_email_files_schemas import (
    post_archive_template_email_files_schema,
    post_create_template_email_files_schema,
)

template_email_files_blueprint = Blueprint(
    "template_email_files",
    __name__,
    url_prefix="/service/<uuid:service_id>/templates/<uuid:template_id>/template_email_files",
)

register_errors(template_email_files_blueprint)


@template_email_files_blueprint.route("", methods=["POST"])
def create_template_email_file(service_id, template_id):
    fetched_service = dao_fetch_service_by_id(service_id=service_id)
    template_email_file_json = validate(request.get_json(), post_create_template_email_files_schema)
    fetched_template = dao_get_template_by_id_and_service_id(template_id, service_id)

    pending = template_email_file_json.get("pending", False)

    if fetched_template.template_type != EMAIL_TYPE:
        raise InvalidRequest(message="Cannot add an email file to a non-email template", status_code=400)

    if not fetched_service.has_permission(EMAIL_TYPE):
        raise InvalidRequest(message="Updating email templates is not allowed", status_code=400)

    template_email_file_json["template_id"] = template_id
    template_email_file = TemplateEmailFile.from_json(template_email_file_json)

    _check_if_filename_unique_for_email_files_within_one_template(template_email_file.filename, template_id)
    if pending:
        dao_create_pending_template_email_file(template_email_file)
    else:
        dao_create_template_email_file(template_email_file)
    return jsonify(data=template_email_files_schema.dump(template_email_file)), 201


@template_email_files_blueprint.route("", methods=["GET"])
def get_template_email_files(service_id, template_id):
    fetched_template_email_files = dao_get_template_email_files_by_template_id(template_id, get_pending=True)
    template_email_files = []
    for template_email_file in fetched_template_email_files:
        template_email_files += [template_email_files_schema.dump(template_email_file)]

    return jsonify(data=template_email_files), 200


@template_email_files_blueprint.route("/<uuid:template_email_file_id>")
def get_template_email_file_by_id(service_id, template_id, template_email_file_id):
    file = dao_get_template_email_file_by_id(template_email_file_id)
    return jsonify(data=template_email_files_schema.dump(file)), 200


@template_email_files_blueprint.route("/<uuid:template_email_file_id>", methods=["POST"])
def update_template_email_file(template_email_file_id, service_id, template_id):
    current_data = TemplateEmailFile.query.filter(TemplateEmailFile.id == template_email_file_id).one()
    current_data_json = template_email_files_schema.dump(current_data)
    updated_data_json = validate(request.get_json(), post_create_template_email_files_schema)
    make_live = updated_data_json.pop("make_live", False)
    updated_data_json = current_data_json | updated_data_json
    # if updated_data_json == current_data_json and not make_live:
    if updated_data_json == current_data_json:
        if make_live:
            updated_email_file = template_email_files_schema.load(updated_data_json)
            updated_email_file.pending = False
            dao_make_pending_template_email_file_live(updated_email_file)
        return jsonify(data=updated_data_json), 200
    updated_email_file = template_email_files_schema.load(updated_data_json)
    if make_live:
        updated_email_file.pending = False
    _check_if_filename_unique_for_email_files_within_one_template(
        updated_email_file.filename, template_id, template_email_file_id
    )
    if make_live or updated_email_file.pending:
        dao_update_pending_template_email_file(updated_email_file)
        return jsonify(data=template_email_files_schema.dump(updated_email_file)), 200
    # if updated_email_file.pending:
    #     dao_update_pending_template_email_file(updated_email_file)
    # else:
    #     dao_update_template_email_file(updated_email_file)
    dao_update_template_email_file(updated_email_file)
    return jsonify(data=template_email_files_schema.dump(updated_email_file)), 200


@template_email_files_blueprint.route("/<uuid:template_email_file_id>/archive", methods=["POST"])
def archive_template_email_file(template_email_file_id, template_id, service_id):
    current_data = TemplateEmailFile.query.get(template_email_file_id)
    current_data_json = template_email_files_schema.dump(current_data)
    updated_data_json = validate(request.get_json(), post_archive_template_email_files_schema)
    updated_data_json = current_data_json | updated_data_json

    updated_data_json["archived_by"] = updated_data_json.pop("archived_by_id")
    updated_data_json["archived_at"] = str(datetime.datetime.utcnow())

    update_dict = template_email_files_schema.load(updated_data_json)

    dao_update_template_email_file(update_dict)

    return jsonify(data=updated_data_json), 200


def _check_if_filename_unique_for_email_files_within_one_template(filename, template_id, template_email_file_id=None):
    email_files = dao_get_template_email_files_by_template_id(template_id)

    if filename in InsensitiveSet(
        email_file.filename for email_file in email_files if email_file.id != template_email_file_id
    ):
        error_message = f"File named {filename} already exists for template id {template_id}"
        raise InvalidRequest(message=error_message, status_code=400)

    return
