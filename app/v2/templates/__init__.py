from flask import Blueprint

from app.v2.errors.errors import register_errors

v2_templates_blueprint = Blueprint("v2_templates", __name__, url_prefix="/v2/templates")

register_errors(v2_templates_blueprint)
