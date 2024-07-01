from flask import Blueprint, current_app, jsonify



unsubscrube_requests_blueprint = Blueprint("unsubscribe_requests", __name__)

@unsubscrube_requests_blueprint.route("/unsubscribe/<uuid:notification_id>", methods=["GET"])
def unsubscribe_requests(notification_id):
    """
    Get all unsubscribe requests, do we want a count as a query string?
    """
    pass

