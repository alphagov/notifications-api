from flask import Blueprint, request
from sqlalchemy.orm.exc import NoResultFound
from template_email_files_schemas import post_create_template_email_files_schema

from app.constants import EMAIL_TYPE
from app.dao.services_dao import dao_fetch_service_by_id
from app.errors import InvalidRequest
from app.models import Template
from app.schema_validation import validate

template_email_files_blueprint = Blueprint(
    "template_email_files", __name__, url_prefix="/service/<uuid:service_id>/<uuid:template_id>/template_email_files"
)


def validate_template_id(template_id, service_id):
    try:
        Template.query.filter(Template.id == template_id, Template.service_id == service_id).one()
    except NoResultFound as e:
        raise InvalidRequest("template_not_found", status_code=400) from e


@template_email_files_blueprint.route("", methods=["POST"])
def create_template(service_id, template_id):
    fetched_service = dao_fetch_service_by_id(service_id=service_id)
    template_email_files_json = validate(request.get_json(), post_create_template_email_files_schema)
    fetched_template = Template.query.filter(
        Template.id == template_id,
        Template.service_id == service_id,
        Template.version == template_email_files_json.get("template_version"),
    )
    if fetched_template.template_type != EMAIL_TYPE:
        raise InvalidRequest(message="cannot create an email for non-email type", status_code=400)
    if not fetched_service.has_permission(EMAIL_TYPE):
        raise InvalidRequest(message="can't create email type", status_code=400)
