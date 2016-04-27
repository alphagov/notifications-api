from flask import (
    Blueprint,
    jsonify,
    request
)

from app.dao.jobs_dao import (
    dao_create_job,
    dao_get_job_by_service_id_and_job_id,
    dao_get_jobs_by_service_id
)

from app.dao.services_dao import (
    dao_fetch_service_by_id
)

from app.schemas import job_schema

from app.celery.tasks import process_job

job = Blueprint('job', __name__, url_prefix='/service/<uuid:service_id>/job')

from app.errors import register_errors

register_errors(job)


@job.route('/<job_id>', methods=['GET'])
def get_job_by_service_and_job_id(service_id, job_id):
    job = dao_get_job_by_service_id_and_job_id(service_id, job_id)
    data, errors = job_schema.dump(job)
    return jsonify(data=data)


@job.route('', methods=['GET'])
def get_jobs_by_service(service_id):
    jobs = dao_get_jobs_by_service_id(service_id)
    data, errors = job_schema.dump(jobs, many=True)
    if errors:
        return jsonify(result="error", message=errors), 400
    return jsonify(data=data)


@job.route('', methods=['POST'])
def create_job(service_id):
    dao_fetch_service_by_id(service_id)

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
