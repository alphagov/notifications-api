from flask import Blueprint

from app.v2.errors import register_errors

v2_returned_letters_blueprint = Blueprint("v2_returned_letters", __name__, url_prefix="/v2/returned-letters")

register_errors(v2_returned_letters_blueprint)
