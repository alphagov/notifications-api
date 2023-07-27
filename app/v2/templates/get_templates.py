from flask import request
from pydantic import BaseModel

from app import authenticated_service
from app.dao import templates_dao
from app.models import TemplateV2Serializer
from app.schema_validation import validate
from app.v2.templates import v2_templates_blueprint
from app.v2.templates.templates_schemas import get_all_template_request


class GetTemplatesResponse(BaseModel):
    templates: list[TemplateV2Serializer]


@v2_templates_blueprint.get("", responses={"200": GetTemplatesResponse})
def get_templates():
    data = validate(request.args.to_dict(), get_all_template_request)

    templates = templates_dao.dao_get_all_templates_for_service(authenticated_service.id, data.get("type"))

    return (
        GetTemplatesResponse(templates=[template.v2_serializer() for template in templates]).json(),
        200,
        {"content-type": "application/json"},
    )
