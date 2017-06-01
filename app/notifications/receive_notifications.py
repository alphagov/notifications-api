from flask import Blueprint
from flask import current_app, jsonify
from flask import request

from app.errors import register_errors

receive_notifications_blueprint = Blueprint('receive_notifications', __name__)
register_errors(receive_notifications_blueprint)


@receive_notifications_blueprint.route('/notifications/sms/receive/mmg', methods=['POST'])
def receive_mmg_sms():
    post_data = request.get_json()
    post_data.pop('MSISDN', None)
    current_app.logger.info("Recieve notification form data: {}".format(post_data))

    return "RECEIVED"


@receive_notifications_blueprint.route('/notifications/sms/receive/firetext', methods=['POST'])
def receive_firetext_sms():
    post_data = request.form
    current_app.logger.info("Received Firetext notification form data: {}".format(post_data))

    return jsonify({
        "status": "ok"
    }), 200
