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

from app.dao.notifications_dao import (
    save_notification,
    get_notification,
    get_notifications
)

from app.schemas import (
    job_schema,
    jobs_schema,
    job_schema_load_json,
    notification_status_schema,
    notifications_status_schema,
    notification_status_schema_load_json
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
        except Exception as e:
            current_app.logger.exception(e)
            return jsonify(result="error", message=str(e)), 500
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
        current_app.logger.exception(e)
        return jsonify(result="error", message=str(e)), 500
    return jsonify(data=job_schema.dump(job).data), 201


@job.route('/<job_id>', methods=['PUT'])
def update_job(service_id, job_id):

    job = get_job(service_id, job_id)
    update_dict, errors = job_schema_load_json.load(request.get_json())
    if errors:
        return jsonify(result="error", message=errors), 400
    try:
        save_job(job, update_dict=update_dict)
    except Exception as e:
        current_app.logger.exception(e)
        return jsonify(result="error", message=str(e)), 500
    return jsonify(data=job_schema.dump(job).data), 200


@job.route('/<job_id>/notification', methods=['POST'])
def create_notification_for_job(service_id, job_id):

    # TODO assert service_id == payload service id
    # and same for job id
    notification, errors = notification_status_schema.load(request.get_json())
    if errors:
        return jsonify(result="error", message=errors), 400
    try:
        save_notification(notification)
    except Exception as e:
        current_app.logger.exception(e)
        return jsonify(result="error", message=str(e)), 500
    return jsonify(data=notification_status_schema.dump(notification).data), 201


@job.route('/<job_id>/notification', methods=['GET'])
@job.route('/<job_id>/notification/<notification_id>')
def get_notification_for_job(service_id, job_id, notification_id=None):
    if notification_id:
        try:
            notification = get_notification(service_id, job_id, notification_id)
            data, errors = notification_status_schema.dump(notification)
            return jsonify(data=data)
        except DataError:
            return jsonify(result="error", message="Invalid notification id"), 400
        except NoResultFound:
            return jsonify(result="error", message="Notification not found"), 404
        except Exception as e:
            current_app.logger.exception(e)
            return jsonify(result="error", message=str(e)), 500
    else:
        notifications = get_notifications(service_id, job_id)
        data, errors = notifications_status_schema.dump(notifications)
        return jsonify(data=data)


@job.route('/<job_id>/notification/<notification_id>', methods=['PUT'])
def update_notification_for_job(service_id, job_id, notification_id):

    notification = get_notification(service_id, job_id, notification_id)
    update_dict, errors = notification_status_schema_load_json.load(request.get_json())

    if errors:
        return jsonify(result="error", message=errors), 400
    try:
        save_notification(notification, update_dict=update_dict)
    except Exception as e:
        current_app.logger.exception(e)
        return jsonify(result="error", message=str(e)), 500

    return jsonify(data=job_schema.dump(notification).data), 200


def _enqueue_job(job):
    aws_region = current_app.config['AWS_REGION']
    queue_name = current_app.config['NOTIFY_JOB_QUEUE']

    queue = boto3.resource('sqs', region_name=aws_region).create_queue(QueueName=queue_name)
    data = {
        'id': str(job.id),
        'service': str(job.service.id),
        'template': job.template.id,
        'bucket_name': job.bucket_name,
        'file_name': job.file_name,
        'original_file_name': job.original_file_name
    }
    job_json = json.dumps(data)
    queue.send_message(MessageBody=job_json,
                       MessageAttributes={'id': {'StringValue': str(job.id), 'DataType': 'String'},
                                          'service': {'StringValue': str(job.service.id), 'DataType': 'String'},
                                          'template': {'StringValue': str(job.template.id), 'DataType': 'String'},
                                          'bucket_name': {'StringValue': job.bucket_name, 'DataType': 'String'},
                                          'file_name': {'StringValue': job.file_name, 'DataType': 'String'},
                                          'original_file_name': {'StringValue': job.original_file_name,
                                                                 'DataType': 'String'}})
