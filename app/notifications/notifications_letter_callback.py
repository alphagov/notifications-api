import json
from functools import wraps

from flask import Blueprint, current_app, jsonify, request
from itsdangerous import BadSignature

from app import signing
from app.celery.process_letter_client_response_tasks import process_letter_callback_data
from app.celery.tasks import (
    record_daily_sorted_counts,
    update_letter_notifications_statuses,
)
from app.config import QueueNames
from app.errors import InvalidRequest
from app.notifications.utils import autoconfirm_subscription
from app.schema_validation import validate
from app.v2.errors import register_errors

letter_callback_blueprint = Blueprint("notifications_letter_callback", __name__)
register_errors(letter_callback_blueprint)


dvla_sns_callback_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "sns callback received on s3 update",
    "type": "object",
    "title": "dvla internal sns callback",
    "properties": {
        "Type": {"enum": ["Notification", "SubscriptionConfirmation"]},
        "MessageId": {"type": "string"},
        "Message": {"type": ["string", "object"]},
    },
    "required": ["Type", "MessageId", "Message"],
}

dvla_letter_callback_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "dvla letter callback schema",
    "type": "object",
    "properties": {
        "specVersion": {"type": "string"},
        "type": {"type": "string"},
        "source": {"type": "string"},
        "id": {"type": "string"},
        "time": {"type": "string", "format": "date-time"},
        "dataContentType": {"type": "string", "enum": ["application/json"]},
        "data": {
            "type": "object",
            "properties": {
                "despatchProperties": {
                    "type": "array",
                    "minItems": 4,
                    "uniqueItems": True,
                    "items": {
                        "type": "object",
                        "properties": {"key": {"type": "string"}, "value": {"type": "string"}},
                        "required": ["key", "value"],
                        "oneOf": [
                            {
                                "properties": {
                                    "key": {"const": "postageClass"},
                                    "value": {"enum": ["1ST", "2ND", "INTERNATIONAL"]},
                                }
                            },
                            {
                                "properties": {
                                    "key": {"const": "mailingProduct"},
                                    "value": {
                                        "enum": ["UNCODED", "MM UNSORTED", "UNSORTED", "MM", "INT EU", "INT ROW"]
                                    },
                                }
                            },
                            {"properties": {"key": {"const": "totalSheets"}, "value": {"type": "string"}}},
                            {"properties": {"key": {"const": "Print Date"}, "value": {"format": "date-time"}}},
                            # if the key does not match the requirements above, do not check values specified previously
                            {
                                "properties": {
                                    "key": {
                                        "not": {"enum": ["postageClass", "mailingProduct", "totalSheets", "Print Date"]}
                                    },
                                }
                            },
                        ],
                    },
                },
                "jobId": {"type": "string"},
                "jobType": {"type": "string"},
                "jobStatus": {"type": "string", "enum": ["DESPATCHED", "REJECTED"]},
                "templateReference": {"type": "string"},
            },
            "required": ["despatchProperties", "jobId", "jobStatus"],
        },
        "metadata": {
            "type": "object",
            "properties": {"correlationId": {"type": "string"}},
            "required": ["correlationId"],
        },
    },
    "required": ["id", "time", "data", "metadata"],
}


def validate_schema(schema):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kw):
            validate(request.get_json(force=True), schema)
            return f(*args, **kw)

        return wrapper

    return decorator


@letter_callback_blueprint.route("/notifications/letter/dvla", methods=["POST"])
@validate_schema(dvla_sns_callback_schema)
def process_letter_response():
    req_json = request.get_json(force=True)
    current_app.logger.debug("Received SNS callback: %s", req_json)
    if not autoconfirm_subscription(req_json):
        # The callback should have one record for an S3 Put Event.
        message = json.loads(req_json["Message"])
        filename = message["Records"][0]["s3"]["object"]["key"]
        current_app.logger.info("Received file from DVLA: %s", filename)

        if filename.lower().endswith("rs.txt") or filename.lower().endswith("rsp.txt"):
            current_app.logger.info("DVLA callback: Calling task to update letter notifications")
            update_letter_notifications_statuses.apply_async([filename], queue=QueueNames.NOTIFY)
            record_daily_sorted_counts.apply_async([filename], queue=QueueNames.NOTIFY)

    return jsonify(result="success", message="DVLA callback succeeded"), 200


@letter_callback_blueprint.route("/notifications/letter/status", methods=["POST"])
@validate_schema(dvla_letter_callback_schema)
def process_letter_callback():
    token = request.args.get("token", "")

    notification_id = parse_token(token)

    request_data = request.get_json()

    if notification_id != request_data["id"]:
        current_app.logger.exception(
            "Notification ID %s in letter callback data does not match token ID %s",
            request_data["id"],
            notification_id,
        )
        raise InvalidRequest("Notification ID in letter callback data does not match ID in token", 400)

    current_app.logger.info("Letter callback for notification id %s received", notification_id)

    despatch_properties = request_data["data"]["despatchProperties"]

    # Since validation guarantees the presence of "totalSheets", we can directly extract it
    page_count = next(item["value"] for item in despatch_properties if item["key"] == "totalSheets")
    status = request_data["data"]["jobStatus"]

    process_letter_callback_data.apply_async(
        kwargs={"notification_id": notification_id, "page_count": page_count, "status": status},
        queue=QueueNames.NOTIFY,
    )

    return jsonify(result="success"), 200


def parse_token(token):
    try:
        notification_id = signing.decode(token)
        return notification_id
    except BadSignature:
        current_app.logger.info("Letter callback with invalid token of %s received", token)
        raise InvalidRequest("A valid token must be provided in the query string", 403) from None
