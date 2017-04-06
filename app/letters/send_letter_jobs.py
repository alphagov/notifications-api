from flask import Blueprint
from flask import request

from app import notify_celery
from app.v2.errors import register_errors
from app.letters.letter_schemas import letter_job_ids
from app.schema_validation import validate

letter_job = Blueprint("letter-job", __name__)
register_errors(letter_job)


@letter_job.route('/send-letter-jobs', methods=['POST'])
def send_letter_jobs():
    job_ids = validate(request.get_json(), letter_job_ids)
    notify_celery.send_task(name="send_files_to_dvla", args=(job_ids['job_ids'],), queue="process-ftp")

    return "Task created to send files to DVLA"
