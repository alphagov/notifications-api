from flask import Blueprint, current_app, jsonify
from datetime import datetime



unsubscrube_requests_blueprint = Blueprint("unsubscribe_requests", __name__)

@unsubscrube_requests_blueprint.route("/unsubscribe/<uuid:notification_id>/summary", methods=["GET"])
def unsubscribe_requests_summary(notification_id):
    pending_unsubscribe_requests = 250
    datetime_of_latest_unsubscribe_request = datetime.now()
    return jsonify(pending_unsubscribe_requests=pending_unsubscribe_requests, datetime_of_latest_unsubscribe_request=datetime_of_latest_unsubscribe_request), 200

