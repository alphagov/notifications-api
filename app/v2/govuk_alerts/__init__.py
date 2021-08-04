from flask import Blueprint

from app.v2.errors import register_errors

v2_govuk_alerts_blueprint = Blueprint(
    "v2_govuk-alerts_blueprint",
    __name__,
    url_prefix='/v2/govuk-alerts',
)

register_errors(v2_govuk_alerts_blueprint)
