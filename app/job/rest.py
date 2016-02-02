import boto3
import json

from flask import (
    Blueprint,
    jsonify,
    request,
    current_app
)

from sqlalchemy.exc import DataError
from sqlalchemy.orm.exc import NoResultFound

from app.dao.jobs_dao import (
    save_job,
    get_job,
    get_jobs_by_service
)

from app.schemas import (
    job_schema,
    jobs_schema
)

job = Blueprint('job', __name__, url_prefix='/service/<service_id>/job')


@job.route('/<job_id>', methods=['GET'])
@job.route('', methods=['GET'])
def get_job_for_service(service_id, job_id=None):
    if job_id:
        try:
            job = get_job(service_id, job_id)
            data, errors = job_schema.dump(job)
            return jsonify(data=data)
        except DataError:
            return jsonify(result="error", message="Invalid job id"), 400
        except NoResultFound:
            return jsonify(result="error", message="Job not found"), 404
    else:
        jobs = get_jobs_by_service(service_id)
        data, errors = jobs_schema.dump(jobs)
        return jsonify(data=data)


@job.route('', methods=['POST'])
def create_job(service_id):
    job, errors = job_schema.load(request.get_json())
    if errors:
        return jsonify(result="error", message=errors), 400
    try:
        save_job(job)
        _enqueue_job(job)
    except Exception as e:
        return jsonify(result="error", message=str(e)), 500
    return jsonify(data=job_schema.dump(job).data), 201


def _enqueue_job(job):
    aws_region = current_app.config['AWS_REGION']
    queue_name = current_app.config['NOTIFY_JOB_QUEUE']

    queue = boto3.resource('sqs', region_name=aws_region).create_queue(QueueName=queue_name)
    job_json = json.dumps({'job_id': str(job.id),  'service_id': str(job.service.id)})
    queue.send_message(MessageBody=job_json,
                       MessageAttributes={'job_id': {'StringValue': str(job.id), 'DataType': 'String'},
                                          'service_id': {'StringValue': str(job.service.id), 'DataType': 'String'}})
