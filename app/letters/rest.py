from flask import Blueprint, jsonify, request

from app.celery.tasks import process_returned_letters_list
from app.config import QueueNames
from app.letters.letter_schemas import letter_references
from app.schema_validation import validate
from app.v2.errors import register_errors

letter_job = Blueprint("letter-job", __name__)
register_errors(letter_job)

# too many references will make SQS error (as the task can only be 256kb)
MAX_REFERENCES_PER_TASK = 5000


@letter_job.route('/letters/returned', methods=['POST'])
def create_process_returned_letters_job():
    references = validate(request.get_json(), letter_references)['references']

    for start_index in range(0, len(references), MAX_REFERENCES_PER_TASK):
        process_returned_letters_list.apply_async(
            args=(references[start_index:start_index + MAX_REFERENCES_PER_TASK], ),
            queue=QueueNames.DATABASE,
            compression='zlib'
        )

    return jsonify(references=references), 200
