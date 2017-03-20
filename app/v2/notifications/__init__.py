from flask import Blueprint
from app.v2.errors import register_errors

v2_notification_blueprint = Blueprint("v2_notifications", __name__, url_prefix='/v2/notifications')

register_errors(v2_notification_blueprint)
