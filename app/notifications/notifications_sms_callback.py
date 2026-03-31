from datetime import UTC, datetime

from flask import Blueprint, json, jsonify, request
from notifications_utils.timezones import local_timezone

from app.celery.process_sms_client_response_tasks import (
    process_sms_client_response,
)
from app.config import QueueNames
from app.errors import InvalidRequest, register_errors

sms_callback_blueprint = Blueprint("sms_callback", __name__, url_prefix="/notifications/sms")
register_errors(sms_callback_blueprint)


@sms_callback_blueprint.route("/mmg", methods=["POST"])
def process_mmg_response():
    uniform_now = datetime.utcnow()
    client_name = "MMG"
    data = json.loads(request.data)
    errors = validate_callback_data(data=data, fields=["status", "CID"], client_name=client_name)
    if errors:
        raise InvalidRequest(errors, status_code=400)

    status = str(data.get("status"))
    detailed_status_code = str(data.get("substatus"))

    provider_reference = data.get("CID")

    delivery_iso_timestamp = None
    try:
        # timestamp with no explicit offset will be in local time :(, convert this into
        # a naive UTC timestamp for further use
        ts = datetime.fromisoformat(data.get("deliverytime") or "")
        delivery_iso_timestamp = (
            ts.replace(tzinfo=ts.tzinfo or local_timezone).astimezone(UTC).replace(tzinfo=None).isoformat()
        )
    except ValueError:
        pass  # None it is, then

    process_sms_client_response.apply_async(
        [
            status,
            provider_reference,
            client_name,
            detailed_status_code,
            delivery_iso_timestamp,
            uniform_now.isoformat(),
        ],
        queue=QueueNames.SMS_CALLBACKS,
    )

    return jsonify(result="success"), 200


@sms_callback_blueprint.route("/firetext", methods=["POST"])
def process_firetext_response():
    uniform_now = datetime.utcnow()
    client_name = "Firetext"
    errors = validate_callback_data(data=request.form, fields=["status", "reference"], client_name=client_name)
    if errors:
        raise InvalidRequest(errors, status_code=400)

    status = request.form.get("status")
    detailed_status_code = request.form.get("code")
    provider_reference = request.form.get("reference")

    delivery_iso_timestamp = None
    try:
        # timestamp with no explicit offset will be in local time :(, convert this into
        # a naive UTC timestamp for further use
        ts = datetime.fromisoformat(request.form.get("time") or "")
        delivery_iso_timestamp = (
            ts.replace(tzinfo=ts.tzinfo or local_timezone).astimezone(UTC).replace(tzinfo=None).isoformat()
        )
    except ValueError:
        pass  # None it is, then

    process_sms_client_response.apply_async(
        [
            status,
            provider_reference,
            client_name,
            detailed_status_code,
            delivery_iso_timestamp,
            uniform_now.isoformat(),
        ],
        queue=QueueNames.SMS_CALLBACKS,
    )

    return jsonify(result="success"), 200


def validate_callback_data(data, fields, client_name):
    errors = []
    for f in fields:
        if not str(data.get(f, "")):
            error = f"{client_name} callback failed: {f} missing"
            errors.append(error)
    return errors if len(errors) > 0 else None
