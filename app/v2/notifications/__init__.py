from flask_openapi3 import APIBlueprint, Tag

from app.openapi import UnauthorizedResponse
from app.v2.errors import register_errors

v2_notification_blueprint = APIBlueprint(
    "v2_notifications",
    __name__,
    url_prefix="/v2/notifications",
    abp_tags=[Tag(name="v2_notifications")],
    abp_security=[{"jwt": []}],
    abp_responses={"401": UnauthorizedResponse},
)

register_errors(v2_notification_blueprint)
