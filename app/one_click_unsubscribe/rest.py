from flask import Blueprint, current_app, jsonify
from itsdangerous import BadData
from notifications_utils.url_safe_token import check_token, generate_token

from app.dao.notifications_dao import get_notification_by_id
from app.dao.unsubscribe_request_dao import create_unsubscribe_request_dao
from app.errors import InvalidRequest, register_errors

one_click_unsubscribe_blueprint = Blueprint("one_click_unsubscribe", __name__)

register_errors(one_click_unsubscribe_blueprint)


@one_click_unsubscribe_blueprint.route("/unsubscribe/<uuid:notification_id>/<string:token>", methods=["POST"])
def one_click_unsubscribe(notification_id, token):
    max_age_seconds = 60 * 60 * 24 * 365  # set to 1 year for now

    try:
        check_token(token, current_app.config["SECRET_KEY"], current_app.config["DANGEROUS_SALT"], max_age_seconds)

    except BadData as e:
        errors = {"unsubscribe request": "This is not a valid unsubscribe link."}
        raise InvalidRequest(errors, status_code=400) from e

    # Create unsubscribe request from the notification object
    notification = get_notification_by_id(notification_id)
    create_unsubscribe_request_dao(notification)

    current_app.logger.debug("Received unsubscribe request for notification_id: %s", notification_id)

    return jsonify(result="success", message="Unsubscribe successful"), 200


def generate_unsubscribe_url_token(data):
    generate_token(str(data), current_app.config["SECRET_KEY"], current_app.config["DANGEROUS_SALT"])
