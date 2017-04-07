from flask import Blueprint, jsonify
from flask import request

from app import notify_celery
from app.dao.jobs_dao import dao_get_all_letter_jobs
from app.schemas import job_schema
from app.v2.errors import register_errors
from app.letters.letter_schemas import letter_job_ids
from app.schema_validation import validate

letter_job = Blueprint("letter-job", __name__)
register_errors(letter_job)


@letter_job.route('/send-letter-jobs', methods=['POST'])
def send_letter_jobs():
    job_ids = validate(request.get_json(), letter_job_ids)
    notify_celery.send_task(name="send-files-to-dvla", args=(job_ids['job_ids'],), queue="process-ftp")

    return "Task created to send files to DVLA"


@letter_job.route('/letter-jobs', methods=['GET'])
def get_letter_jobs():
    letter_jobs = dao_get_all_letter_jobs()
    data = job_schema.dump(letter_jobs, many=True).data

    return jsonify(data=data), 200
