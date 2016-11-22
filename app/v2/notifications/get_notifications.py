from flask import jsonify

from app import api_user
from app.dao import notifications_dao
from app.v2.notifications import notification_blueprint


@notification_blueprint.route("/<uuid:id>", methods=['GET'])
def get_notification_by_id(id):
    notification = notifications_dao.get_notification_with_personalisation(
        str(api_user.service_id), id, key_type=None
    )

    return jsonify(notification.serialize()), 200


@notification_blueprint.route("/", methods=['GET'])
def get_notifications():
    # validate notifications request arguments
    # fetch all notifications
    # return notifications_response schema
    pass
