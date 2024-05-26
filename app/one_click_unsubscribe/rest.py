from flask import Blueprint, jsonify, current_app
from app.errors import InvalidRequest, register_errors
from app.dao.notifications_dao import get_notification_by_id
from notifications_utils.url_safe_token import check_token, generate_token

one_click_unsubscribe_blueprint = Blueprint("one_click_unsubscribe", __name__)

register_errors(one_click_unsubscribe_blueprint)


@one_click_unsubscribe_blueprint.route("/unsubscribe/<uuid:notification_id>/<string:token>", methods=["POST"])
def one_click_unsubscribe(notification_id, token):
    max_age_seconds = 60 * 60 * 24 * 365  # set to 1 year for now
    email_address = check_token(token, current_app.config["SECRET_KEY"], current_app.config["DANGEROUS_SALT"],
                                max_age_seconds)
    notification = get_notification_by_id(notification_id)
    unsubscribe_data = {
        "notification_id": notification_id,
        "template_id": notification.template_id,
        "template_version": notification.template_version,
        "service_id": notification.service_id,
        "email_address": email_address

    }

    current_app.logger.debug("Received unsubscribe request for notification_id: %s", notification_id)

    # TODO
    # Once the migration for the new unsubscribe request table has been effected, write a dao method needs to
    # add new unsubscribe request:
    # unsubscribe_request = UnsubscribeRequest(**unsubscribe_data)

    return jsonify(result="success", message="Unsubscribe successful"), 200


def generate_unsubscribe_url_token(email_address):
    generate_token(email_address,current_app.config["SECRET_KEY"], current_app.config["DANGEROUS_SALT"])
