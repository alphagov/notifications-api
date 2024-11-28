from datetime import datetime
from urllib.parse import unquote

import iso8601
from flask import Blueprint, abort, current_app, jsonify, request
from gds_metrics.metrics import Counter
from notifications_utils.recipient_validation.phone_number import try_validate_and_format_phone_number

from app.celery import service_callback_tasks
from app.config import QueueNames
from app.constants import INBOUND_SMS_TYPE
from app.dao.inbound_sms_dao import dao_create_inbound_sms
from app.dao.services_dao import dao_fetch_service_by_inbound_number
from app.errors import register_errors
from app.models import InboundSms

receive_notifications_blueprint = Blueprint("receive_notifications", __name__)
register_errors(receive_notifications_blueprint)


INBOUND_SMS_COUNTER = Counter("inbound_sms", "Total number of inbound SMS received", ["provider"])


@receive_notifications_blueprint.route("/notifications/sms/receive/mmg", methods=["POST"])
def receive_mmg_sms():
    """
    {
        'MSISDN': '447123456789'
        'Number': '40604',
        'Message': 'some+uri+encoded+message%3A',
        'ID': 'SOME-MMG-SPECIFIC-ID',
        'DateRecieved': '2017-05-21+11%3A56%3A11'
    }
    """
    post_data = request.get_json()

    auth = request.authorization

    if not auth:
        current_app.logger.warning("Inbound sms (MMG) no auth header")
        abort(401)
    elif (
        auth.username not in current_app.config["MMG_INBOUND_SMS_USERNAME"]
        or auth.password not in current_app.config["MMG_INBOUND_SMS_AUTH"]
    ):
        current_app.logger.warning("Inbound sms (MMG) incorrect username (%s) or password", auth.username)
        abort(403)

    inbound_number = strip_leading_forty_four(post_data["Number"])

    service = fetch_potential_service(inbound_number, "mmg")
    if not service:
        # since this is an issue with our service <-> number mapping, or no inbound_sms service permission
        # we should still tell MMG that we received it successfully
        return "RECEIVED", 200

    INBOUND_SMS_COUNTER.labels("mmg").inc()

    inbound = create_inbound_sms_object(
        service,
        content=format_mmg_message(post_data["Message"]),
        from_number=post_data["MSISDN"],
        provider_ref=post_data["ID"],
        date_received=post_data.get("DateRecieved"),
        provider_name="mmg",
    )

    service_callback_tasks.send_inbound_sms_to_service.apply_async(
        [str(inbound.id), str(service.id)], queue=QueueNames.CALLBACKS
    )

    current_app.logger.debug(
        "%s received inbound SMS with reference %s from MMG", service.id, inbound.provider_reference
    )
    return jsonify({"status": "ok"}), 200


@receive_notifications_blueprint.route("/notifications/sms/receive/firetext", methods=["POST"])
def receive_firetext_sms():
    post_data = request.form

    auth = request.authorization
    if not auth:
        current_app.logger.warning("Inbound sms (Firetext) no auth header")
        abort(401)
    elif auth.username != "notify" or auth.password not in current_app.config["FIRETEXT_INBOUND_SMS_AUTH"]:
        current_app.logger.warning("Inbound sms (Firetext) incorrect username (%s) or password", auth.username)
        abort(403)

    inbound_number = strip_leading_forty_four(post_data["destination"])

    service = fetch_potential_service(inbound_number, "firetext")
    if not service:
        return jsonify({"status": "ok"}), 200

    inbound = create_inbound_sms_object(
        service=service,
        content=post_data["message"],
        from_number=post_data["source"],
        provider_ref=None,
        date_received=post_data["time"],
        provider_name="firetext",
    )

    INBOUND_SMS_COUNTER.labels("firetext").inc()

    service_callback_tasks.send_inbound_sms_to_service.apply_async(
        [str(inbound.id), str(service.id)], queue=QueueNames.CALLBACKS
    )
    current_app.logger.debug(
        "%s received inbound SMS with reference %s from Firetext", service.id, inbound.provider_reference
    )
    return jsonify({"status": "ok"}), 200


def format_mmg_message(message):
    return unescape_string(unquote(message.replace("+", " ")))


def unescape_string(string):
    return string.encode("raw_unicode_escape").decode("unicode_escape")


def format_mmg_datetime(date):
    """
    We expect datetimes in format 2017-05-21+11%3A56%3A11 - ie, spaces replaced with pluses, and URI encoded
    and in UTC
    """
    try:
        orig_date = format_mmg_message(date)
        parsed_datetime = iso8601.parse_date(orig_date).replace(tzinfo=None)
        return parsed_datetime
    except iso8601.ParseError:
        return datetime.utcnow()


def create_inbound_sms_object(service, content, from_number, provider_ref, date_received, provider_name):
    user_number = try_validate_and_format_phone_number(
        from_number, international=True, log_msg=f'Invalid from_number received for service "{service.id}"'
    )

    provider_date = date_received
    if provider_date:
        provider_date = format_mmg_datetime(provider_date)

    inbound = InboundSms(
        service=service,
        notify_number=service.get_inbound_number(),
        user_number=user_number,
        provider_date=provider_date,
        provider_reference=provider_ref,
        content=content,
        provider=provider_name,
    )
    dao_create_inbound_sms(inbound)
    return inbound


def fetch_potential_service(inbound_number, provider_name):
    service = dao_fetch_service_by_inbound_number(inbound_number)

    if not service:
        current_app.logger.warning(
            'Inbound number "%s" from %s not associated with a service', inbound_number, provider_name
        )
        return False

    if not has_inbound_sms_permissions(service.permissions):
        current_app.logger.error('Service "%s" does not allow inbound SMS', service.id)
        return False

    return service


def has_inbound_sms_permissions(permissions):
    str_permissions = [p.permission for p in permissions]
    return INBOUND_SMS_TYPE in str_permissions


def strip_leading_forty_four(number):
    if number.startswith("44"):
        return number.replace("44", "0", 1)
    return number
