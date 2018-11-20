from flask import Blueprint, jsonify
from flask import request

from app.celery.tasks import process_returned_letters_list
from app.config import QueueNames
from app.letters.letter_schemas import letter_references
from app.schema_validation import validate
from app.v2.errors import register_errors

letter_job = Blueprint("letter-job", __name__)
register_errors(letter_job)


@letter_job.route('/letters/returned', methods=['POST'])
def create_process_returned_letters_job():
    references = validate(request.get_json(), letter_references)

    process_returned_letters_list.apply_async([references['references']], queue=QueueNames.DATABASE)

    return jsonify(references=references['references']), 200
