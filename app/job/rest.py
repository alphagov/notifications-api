from flask import (
    Blueprint,
    jsonify,
    request
)

from app.dao.jobs_dao import (
    dao_create_job,
    dao_get_job_by_service_id_and_job_id,
    dao_get_jobs_by_service_id,
    dao_update_job
)

from app.dao.services_dao import (
    dao_fetch_service_by_id
)

from app.schemas import (
    job_schema,
    job_schema_load_json,
    notification_status_schema,
    notification_status_schema_load_json
)

from app.celery.tasks import process_job

job = Blueprint('job', __name__, url_prefix='/service/<service_id>/job')

from app.errors import register_errors

register_errors(job)


@job.route('/<job_id>', methods=['GET'])
def get_job_by_service_and_job_id(service_id, job_id):
    job = dao_get_job_by_service_id_and_job_id(service_id, job_id)
    if not job:
        return jsonify(result="error", message="Job {} not found for service {}".format(job_id, service_id)), 404
    data, errors = job_schema.dump(job)
    return jsonify(data=data)


@job.route('', methods=['GET'])
def get_jobs_by_service(service_id):
    jobs = dao_get_jobs_by_service_id(service_id)
    data, errors = job_schema.dump(jobs, many=True)
    return jsonify(data=data)


@job.route('', methods=['POST'])
def create_job(service_id):

    service = dao_fetch_service_by_id(service_id)
    if not service:
        return jsonify(result="error", message="Service {} not found".format(service_id)), 404

    data = request.get_json()
    data.update({
        "service": service_id
    })
    job, errors = job_schema.load(data)
    if errors:
        return jsonify(result="error", message=errors), 400

    dao_create_job(job)
    process_job.apply_async([str(job.id)], queue="process-job")
    return jsonify(data=job_schema.dump(job).data), 201


@job.route('/<job_id>', methods=['POST'])
def update_job(service_id, job_id):
    fetched_job = dao_get_job_by_service_id_and_job_id(service_id, job_id)
    if not fetched_job:
        return jsonify(result="error", message="Job {} not found for service {}".format(job_id, service_id)), 404

    current_data = dict(job_schema.dump(fetched_job).data.items())
    current_data.update(request.get_json())

    update_dict, errors = job_schema.load(current_data)
    if errors:
        return jsonify(result="error", message=errors), 400
    dao_update_job(update_dict)
    return jsonify(data=job_schema.dump(update_dict).data), 200
