import datetime
import uuid
from dataclasses import dataclass

from flask import Blueprint, current_app, request
from itsdangerous import BadSignature
from jsonschema import ValidationError

from app import signing
from app.celery.process_letter_client_response_tasks import process_letter_callback_data
from app.config import QueueNames
from app.constants import DVLA_NOTIFICATION_DISPATCHED, DVLA_NOTIFICATION_REJECTED
from app.errors import InvalidRequest
from app.models import LetterCostThreshold
from app.schema_validation import validate
from app.v2.errors import register_errors

letter_callback_blueprint = Blueprint("notifications_letter_callback", __name__)
register_errors(letter_callback_blueprint)


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
                                        "enum": [
                                            "UNCODED",
                                            "MM UNSORTED",
                                            "UNSORTED",
                                            "MM",
                                            "INT EU",
                                            "INT ROW",
                                            "UNSORTEDE",
                                            "MM ECONOMY",
                                        ]
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
                "jobId": {"type": "string", "format": "uuid"},
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


@letter_callback_blueprint.route("/notifications/letter/status", methods=["POST"])
def process_letter_callback():
    token = request.args.get("token", "")
    notification_id = parse_token(token)

    request_data = request.get_json(force=True)
    try:
        validate(request_data, dvla_letter_callback_schema)
    except ValidationError:
        current_app.logger.error("Received invalid json schema: %s", request_data)
        raise

    current_app.logger.info("Letter callback for notification id %s received", notification_id)

    check_token_matches_payload(token_id=notification_id, json_id=request_data["data"]["jobId"])

    letter_update = extract_properties_from_request(request_data)

    process_letter_callback_data.apply_async(
        kwargs={
            "notification_id": uuid.UUID(notification_id),
            "page_count": letter_update.page_count,
            "dvla_status": letter_update.status,
            "cost_threshold": letter_update.cost_threshold,
            "despatch_date": letter_update.despatch_date,
        },
        queue=QueueNames.LETTER_CALLBACKS,
    )

    return {}, 204


def parse_token(token):
    try:
        notification_id = signing.decode(token)
        return notification_id
    except BadSignature:
        current_app.logger.info("Letter callback with invalid token of %s received", token)
        raise InvalidRequest("A valid token must be provided in the query string", 403) from None


def check_token_matches_payload(token_id, json_id):
    if token_id != json_id:
        current_app.logger.exception(
            "Notification ID in token does not match json. token: %s - json: %s",
            token_id,
            json_id,
        )
        raise InvalidRequest("Notification ID in letter callback data does not match ID in token", 400)


@dataclass
class LetterUpdate:
    page_count: int
    status: str
    cost_threshold: LetterCostThreshold
    despatch_date: datetime.date


def extract_properties_from_request(request_data) -> LetterUpdate:
    despatch_properties = request_data["data"]["despatchProperties"]

    # Since validation guarantees the presence of "totalSheets", we can directly extract it
    page_count = int(next(item["value"] for item in despatch_properties if item["key"] == "totalSheets"))
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
    if (mailing_product == "MM" or mailing_product == "MM ECONOMY") and postage == "2ND":
        return LetterCostThreshold("sorted")
    return LetterCostThreshold("unsorted")


def _get_despatch_date(despatch_datetime: str) -> datetime.date:
    """
    Converts a datetime string in the format of 2024-10-15 04:00:16.287 to a date.
    Both the despatch_date argument and date returned are in London local time.
    """
    return datetime.datetime.strptime(despatch_datetime, "%Y-%m-%d %H:%M:%S.%f").date()
