from flask import Blueprint

from app.v2.errors import register_errors

v2_template_blueprint = Blueprint("v2_template", __name__, url_prefix='/v2/template')

register_errors(v2_template_blueprint)
