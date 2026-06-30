from flask import jsonify, request

from app import api_user, authenticated_service
from app.dao.returned_letters_dao import count_orphaned_returned_letters, fetch_returned_letter_summary
from app.errors import InvalidRequest
from app.schema_validation import validate
from app.service.rest import _fetch_returned_letter_data
from app.utils import DATE_FORMAT
from app.v2.returned_letters import v2_returned_letters_blueprint
from app.v2.returned_letters.get_returned_letters_schema import get_returned_letters_request


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


@v2_returned_letters_blueprint.route("/", methods=["GET"])
def get_returned_letters():
    """
    This endpoint returns the latest returned letters for a service
    """
    if api_user.key_type != "normal":
        raise InvalidRequest("Only live API keys are authorised to get the latest returned letter summary.", 403)

    service_id = str(authenticated_service.id)
    data = validate(request.args.to_dict(), get_returned_letters_request)
    report_date = data.get("report_date")
    result = [
        {
            "notification_id": str(row["notification_id"]),
            "reference": row["client_reference"],
            "report_date": row["reported_at"],
            "created_at": row["created_at"],
            "email_address": row["email_address"],
            "template_name": str(row["template_name"]),
            "template_id": str(row["template_id"]),
            "template_version": row["template_version"],
            "spreadsheet_file_name": row["original_file_name"],
            "spreadsheet_row_number": row["job_row_number"],
            "uploaded_letter_file_name": row["uploaded_letter_file_name"],
        }
        for row in _fetch_returned_letter_data(service_id, report_date)
    ]

    return {
        "returned_letters": sorted(result, key=lambda i: i["created_at"], reverse=True),
        "orphaned_count": count_orphaned_returned_letters(service_id, report_date),
    }
