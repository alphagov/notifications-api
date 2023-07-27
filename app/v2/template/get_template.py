import uuid
from typing import Optional

from pydantic import BaseModel, Field

from app import authenticated_service
from app.dao import templates_dao
from app.models import TemplateV2Serializer
from app.v2.template import v2_template_blueprint


class GetTemplatePath(BaseModel):
    template_id: uuid.UUID


@v2_template_blueprint.get("/<template_id>", responses={"200": TemplateV2Serializer})
def get_template_by_id(path: GetTemplatePath):
    template = templates_dao.dao_get_template_by_id_and_service_id(path.template_id, authenticated_service.id)
    return template.v2_serializer().json(), 200, {"content-type": "application/json"}


class GetTemplateVersionPath(GetTemplatePath):
    version: Optional[int] = Field(ge=1)


@v2_template_blueprint.get("/<template_id>/version/<int:version>", responses={"200": TemplateV2Serializer})
def get_template_version_by_id(path: GetTemplateVersionPath):
    template = templates_dao.dao_get_template_by_id_and_service_id(
        path.template_id, authenticated_service.id, path.version
    )
    return template.v2_serializer().json(), 200, {"content-type": "application/json"}
