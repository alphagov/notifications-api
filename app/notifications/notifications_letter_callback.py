import datetime
import json
from dataclasses import dataclass

from flask import Blueprint, current_app, jsonify, request
from itsdangerous import BadSignature

from app import signing
from app.celery.process_letter_client_response_tasks import process_letter_callback_data
from app.celery.tasks import (
    record_daily_sorted_counts,
    update_letter_notifications_statuses,
)
from app.config import QueueNames
from app.constants import DVLA_NOTIFICATION_DISPATCHED, DVLA_NOTIFICATION_REJECTED
from app.errors import InvalidRequest
from app.models import LetterCostThreshold
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
                            {
                                "properties": {
                                    "key": {"const": "productionRunDate"},
                                    "value": {"type": "string", "format": "letter_production_run_date"},
                                }
                            },
                            # if the key does not match the requirements above, do not check values specified previously
                            {
                                "properties": {
                                    "key": {
                                        "not": {
                                            "enum": [
                                                "postageClass",
                                                "mailingProduct",
                                                "totalSheets",
                                                "productionRunDate",
                                            ]
                                        }
                                    },
                                }
                            },
                        ],
                    },
                },
                "jobId": {"type": "string"},
                "jobType": {"type": "string"},
                "jobStatus": {"type": "string", "enum": [DVLA_NOTIFICATION_DISPATCHED, DVLA_NOTIFICATION_REJECTED]},
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


@letter_callback_blueprint.route("/notifications/letter/dvla", methods=["POST"])
def process_letter_response():
    req_json = request.get_json(force=True)
    validate(req_json, dvla_sns_callback_schema)

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
def process_letter_callback():
    token = request.args.get("token", "")
    notification_id = parse_token(token)

    request_data = request.get_json(force=True)
    validate(request_data, dvla_letter_callback_schema)

    current_app.logger.info("Letter callback for notification id %s received", notification_id)

    check_token_matches_payload(notification_id, request_data["id"])

    letter_update = extract_properties_from_request(request_data)

    process_letter_callback_data.apply_async(
        kwargs={
            "notification_id": notification_id,
            "page_count": letter_update.page_count,
            "status": letter_update.status,
            "cost_threshold": letter_update.cost_threshold,
            "despatch_date": letter_update.despatch_date,
        },
        queue=QueueNames.NOTIFY,
    )

    return {}, 204


def parse_token(token):
    try:
        notification_id = signing.decode(token)
        return notification_id
    except BadSignature:
        current_app.logger.info("Letter callback with invalid token of %s received", token)
        raise InvalidRequest("A valid token must be provided in the query string", 403) from None


def check_token_matches_payload(notification_id, request_id):
    if notification_id != request_id:
        current_app.logger.exception(
            "Notification ID %s in letter callback data does not match token ID %s",
            notification_id,
            request_id,
        )
        raise InvalidRequest("Notification ID in letter callback data does not match ID in token", 400)


@dataclass
class LetterUpdate:
    page_count: str
    status: str
    cost_threshold: LetterCostThreshold
    despatch_date: str


def extract_properties_from_request(request_data) -> LetterUpdate:
    despatch_properties = request_data["data"]["despatchProperties"]

    # Since validation guarantees the presence of "totalSheets", we can directly extract it
    page_count = next(item["value"] for item in despatch_properties if item["key"] == "totalSheets")
    status = request_data["data"]["jobStatus"]

    mailing_product = next(item["value"] for item in despatch_properties if item["key"] == "mailingProduct")
    postage = next(item["value"] for item in despatch_properties if item["key"] == "postageClass")
    cost_threshold = _get_cost_threshold(mailing_product, postage)

    despatch_datetime = next(item["value"] for item in despatch_properties if item["key"] == "productionRunDate")
    despatch_date = _get_despatch_date(despatch_datetime)

    return LetterUpdate(
        page_count=page_count,
        status=status,
        cost_threshold=cost_threshold,
        despatch_date=despatch_date,
    )


def _get_cost_threshold(mailing_product: str, postage: str) -> LetterCostThreshold:
    if mailing_product == "MM" and postage == "2ND":
        return LetterCostThreshold("sorted")

    return LetterCostThreshold("unsorted")


def _get_despatch_date(despatch_datetime: str) -> datetime.date:
    """
    Converts a datetime string in the format of 2024-10-15 04:00:16.287 to a date.
    Both the despatch_date argument and date returned are in London local time.
    """
    return datetime.datetime.strptime(despatch_datetime, "%Y-%m-%d %H:%M:%S.%f").date()
