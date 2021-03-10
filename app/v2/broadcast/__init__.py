from flask import Blueprint

from app.v2.errors import register_errors

v2_broadcast_blueprint = Blueprint(
    "v2_broadcast_blueprint",
    __name__,
    url_prefix='/v2/broadcast',
)

register_errors(v2_broadcast_blueprint)
