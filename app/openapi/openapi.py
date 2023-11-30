import json

from apispec import APISpec
from flask import Blueprint

openapi_blueprint = Blueprint("openapi", __name__, url_prefix="/openapi")


def setup_openapi(application, openapi_spec: APISpec):
    from app import schemas
    from app.v2.notifications.post_notifications import (
        post_email_notification,
        post_letter_notification,
        post_sms_notification,
    )

    with application.test_request_context():
        openapi_spec.components.schema("Notification", schema=schemas.notification_schema)
        openapi_spec.path(view=post_sms_notification)
        openapi_spec.path(view=post_email_notification)
        openapi_spec.path(view=post_letter_notification)


@openapi_blueprint.route("/", methods=["GET"])
def get_openapi_spec():
    from app import openapi_spec

    return json.dumps(openapi_spec.to_dict()), 200, {"content-type": "application/json"}
