from flask import Blueprint, request
from sqlalchemy.orm.exc import NoResultFound

from app.errors import InvalidRequest
from app.models import Template, TemplateEmailFile
import uuid

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
    template_email_files_json = request.json
    validate_template_id(template_id, service_id) # make sure it exists
    template_email_file = TemplateEmailFile()
    template_email_file.id = uuid.uuid4()
    template_email_file.filename = "test filename"
