from flask import Blueprint, jsonify, request
from sqlalchemy.orm.exc import NoResultFound

from app import db
from app.constants import EMAIL_TYPE
from app.dao.dao_utils import autocommit
from app.dao.services_dao import dao_fetch_service_by_id
from app.errors import InvalidRequest
from app.models import Template, TemplateEmailFile
from app.schema_validation import validate
from app.schemas import template_email_files_schema
from app.template_email_files.template_email_files_schemas import post_create_template_email_files_schema

template_email_files_blueprint = Blueprint(
    "template_email_files", __name__, url_prefix="/service/<uuid:service_id>/<uuid:template_id>/template_email_files"
)


def validate_template_id(template_id, service_id):
    try:
        Template.query.filter(Template.id == template_id, Template.service_id == service_id).one()
    except NoResultFound as e:
        raise InvalidRequest("template_not_found", status_code=400) from e


@autocommit
def dao_create_template_email_files(template_email_file: TemplateEmailFile):
    db.session.add(template_email_file)


@autocommit
def dao_get_template_email_files_by_template_id_and_version(template_id, template_version):
    pass


@template_email_files_blueprint.route("", methods=["POST"])
def create_template_email_files(service_id, template_id):
    fetched_service = dao_fetch_service_by_id(service_id=service_id)
    template_email_files_json = validate(request.get_json(), post_create_template_email_files_schema)
    fetched_template = Template.query.filter(
        Template.id == template_id,
        Template.service_id == service_id,
        Template.version == template_email_files_json.get("template_version"),
    ).one()
    if fetched_template.template_type != EMAIL_TYPE:
        raise InvalidRequest(message="cannot create an email for non-email type", status_code=400)
    if not fetched_service.has_permission(EMAIL_TYPE):
        raise InvalidRequest(message="can't create email type", status_code=400)
    template_email_file = TemplateEmailFile.from_json(template_email_files_json)
    dao_create_template_email_files(template_email_file)
    return jsonify(data=template_email_files_schema.dump(template_email_file)), 201


@template_email_files_blueprint.route("", methods=["GET"])
def get_template_email_files(service_id, template_id):
    fetched_template = Template.query.filter(
        Template.id == template_id,
        Template.service_id == service_id,
    ).one()

    fetched_template_email_files = TemplateEmailFile.query.filter(
        TemplateEmailFile.template_id == fetched_template.id,
        TemplateEmailFile.template_version == fetched_template.version,
    ).all()

    template_email_files = []
    for template_email_file in fetched_template_email_files:
        template_email_files+=[template_email_files_schema.dump(template_email_file)]

    return jsonify(data=template_email_files), 201
