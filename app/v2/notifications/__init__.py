from flask import Blueprint

from app.v2.errors import register_errors

notification_blueprint = Blueprint(__name__, __name__, url_prefix='/v2/notifications')

register_errors(notification_blueprint)
