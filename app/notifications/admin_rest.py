from flask import Blueprint, jsonify

from app.dao import notifications_dao
from app.errors import register_errors

admin_notifications_blueprint = Blueprint("admin_notifications", __name__)

register_errors(admin_notifications_blueprint)


@admin_notifications_blueprint.route("/notifications/<uuid:notification_id>/events", methods=["GET"])
def get_notification_events(notification_id):
    events = notifications_dao.get_notification_events_by_notification_id(notification_id=notification_id)
    return jsonify(events=[event.serialize() for event in events]), 200
