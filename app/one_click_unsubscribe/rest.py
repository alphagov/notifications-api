from flask import Blueprint, current_app, jsonify
from itsdangerous import BadData
from notifications_utils.url_safe_token import check_token

from app import redis_store
from app.dao.notification_history_dao import get_notification_history_by_id
from app.dao.notifications_dao import get_notification_by_id
from app.dao.unsubscribe_request_dao import (
    create_unsubscribe_request_dao,
    get_unbatched_unsubscribe_requests_dao,
    get_unsubscribe_request_reports_dao,
)
from app.errors import InvalidRequest, register_errors
from app.models import UnsubscribeRequestReport

one_click_unsubscribe_blueprint = Blueprint("one_click_unsubscribe", __name__)

register_errors(one_click_unsubscribe_blueprint)


@one_click_unsubscribe_blueprint.route("/unsubscribe/<uuid:notification_id>/<string:token>", methods=["POST"])
def one_click_unsubscribe(notification_id, token):
    max_age_seconds = 60 * 60 * 24 * 365  # set to 1 year for now

    try:
        email_address = check_token(
            token, current_app.config["SECRET_KEY"], current_app.config["DANGEROUS_SALT"], max_age_seconds
        )
    except BadData as e:
        errors = {"unsubscribe request": "This is not a valid unsubscribe link."}
        raise InvalidRequest(errors, status_code=404) from e

    if notification := get_notification_by_id(notification_id):
        unsubscribe_data = get_unsubscribe_request_data(notification, email_address)

    # if it is past the retention period for the service, then search the notifications_history table
    elif notification := get_notification_history_by_id(notification_id):
        unsubscribe_data = get_unsubscribe_request_data(notification, email_address)

    # if there is no match on both the Notifications and Notifications History tables, the unsubscribe request
    # is deemed invalid
    else:
        errors = {"unsubscribe request": "This is not a valid unsubscribe link."}
        raise InvalidRequest(errors, status_code=404)

    create_unsubscribe_request_dao(unsubscribe_data)
    redis_store.delete(f"service-{unsubscribe_data['service_id']}-unsubscribe-request-statistics")

    current_app.logger.debug("Received unsubscribe request for notification_id: %s", notification_id)

    return jsonify(result="success", message="Unsubscribe successful"), 200


def get_unsubscribe_request_data(notification, email_address):
    return {  # noqa
        "notification_id": notification.id,
        "template_id": notification.template_id,
        "template_version": notification.template_version,
        "service_id": notification.service_id,
        "email_address": email_address,
    }


def create_unsubscribe_request_reports_summary(service_id):
    reports_summary = []
    batched_unsubscribe_reports_summary = []
    unbatched_unsubscribe_report_summary = []
    # Check for existing unsubscribe reports and create their summaries
    if unsubscribe_request_reports := get_unsubscribe_request_reports_dao(service_id):
        batched_unsubscribe_reports_summary = _create_batched_unsubscribe_request_reports_summary(
            unsubscribe_request_reports,
        )
        batched_unsubscribe_reports_summary = batched_unsubscribe_reports_summary
    # Check for unsubscribe requests and create a summary for them
    if unbatched_unsubscribe_requests := get_unbatched_unsubscribe_requests_dao(service_id):
        unbatched_unsubscribe_report_summary.append(
            _create_unbatched_unsubscribe_request_report_summary(unbatched_unsubscribe_requests)
        )
    reports_summary = unbatched_unsubscribe_report_summary + batched_unsubscribe_reports_summary

    return reports_summary


def _create_batched_unsubscribe_request_reports_summary(unsubscribe_request_reports: list) -> list:
    return [report.serialize() for report in unsubscribe_request_reports]


def _create_unbatched_unsubscribe_request_report_summary(unbatched_unsubscribe_requests: list) -> dict:
    return UnsubscribeRequestReport.serialize_unbatched_requests(unbatched_unsubscribe_requests)
