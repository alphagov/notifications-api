from flask import Blueprint, jsonify, request

from app.celery.tasks import process_returned_letters_list
from app.config import QueueNames
from app.dao.letter_rate_dao import dao_get_current_letter_rates
from app.dao.returned_letters_dao import fetch_returned_letters
from app.letters.letter_schemas import letter_references
from app.schema_validation import validate
from app.utils import DATE_FORMAT, DATETIME_FORMAT_NO_TIMEZONE
from app.v2.errors import register_errors

letter_job = Blueprint("letter-job", __name__)
letter_rates_blueprint = Blueprint("letter_rates", __name__, url_prefix="/letter-rates")
register_errors(letter_job)
register_errors(letter_rates_blueprint)

# too many references will make SQS error (as the task can only be 256kb)
MAX_REFERENCES_PER_TASK = 5000


@letter_job.route("/letters/returned", methods=["POST"])
def create_process_returned_letters_job():
    references = validate(request.get_json(), letter_references)["references"]

    for start_index in range(0, len(references), MAX_REFERENCES_PER_TASK):
        process_returned_letters_list.apply_async(
            args=(references[start_index : start_index + MAX_REFERENCES_PER_TASK],),
            queue=QueueNames.DATABASE,
            compression="zlib",
        )

    return jsonify(references=references), 200


@letter_rates_blueprint.route("/", methods=["GET"])
def get_letter_rates():
    return jsonify([rate.serialize() for rate in dao_get_current_letter_rates()])


def fetch_returned_letter_data(service_id, report_date):
    results = fetch_returned_letters(service_id=service_id, report_date=report_date)
    json_results = [
        {
            "notification_id": x.notification_id,
            # client reference can only be added on API letters
            "client_reference": x.client_reference if x.api_key_id else None,
            "reported_at": x.reported_at.strftime(DATE_FORMAT),
            "created_at": x.created_at.strftime(DATETIME_FORMAT_NO_TIMEZONE),
            # it doesn't make sense to show hidden/precompiled templates
            "template_name": x.template_name if not x.hidden else None,
            "template_id": x.template_id if not x.hidden else None,
            "template_version": x.template_version if not x.hidden else None,
            "user_name": x.user_name or "API",
            "email_address": x.email_address or "API",
            "original_file_name": x.original_file_name,
            "job_row_number": x.job_row_number,
            # the file name for a letter uploaded via the UI
            "uploaded_letter_file_name": x.client_reference if x.hidden and not x.api_key_id else None,
        }
        for x in results
    ]
    return json_results
