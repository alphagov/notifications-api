from flask_openapi3 import APIBlueprint, Tag

from app.openapi import UnauthorizedResponse
from app.v2.errors import register_errors

v2_templates_blueprint = APIBlueprint(
    "v2_templates",
    __name__,
    url_prefix="/v2/templates",
    abp_tags=[Tag(name="v2_templates")],
    abp_security=[{"jwt": []}],
    abp_responses={"401": UnauthorizedResponse},
)

register_errors(v2_templates_blueprint)
