from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from flask import abort, jsonify, make_response, request
from notifications_utils.clients.redis import RequestCache

from app import authenticated_service, redis_store, api_user
from app.dao.returned_letters_dao import fetch_returned_letter_summary
from app.errors import InvalidRequest
from app.schema_validation import validate
from app.utils import DATE_FORMAT
from app.v2.returned_letters import v2_returned_letters_blueprint


@v2_returned_letters_blueprint.route("/summary", methods=["GET"])
def get_returned_letter_summary():
    """
    This endpoint returns the existing returned letters summaries for a service
    """
    if api_user.key_type != "normal":
        raise InvalidRequest("Only live API keys are authorised to get the latest returned letter summary.", 403)

    service_id = str(authenticated_service.id)

    data = [
        {"returned_letter_count": row.returned_letter_count, "report_date": row.reported_at.strftime(DATE_FORMAT)}
        for row in fetch_returned_letter_summary(service_id)
    ]

    if not data:
        return jsonify({"returned_letter_count": 0, "report_date": None}), 200

    return jsonify(data), 200


