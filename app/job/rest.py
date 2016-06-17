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

from app.dao.templates_dao import (dao_get_template_by_id)

from app.schemas import job_schema, unarchived_template_schema

from app.celery.tasks import process_job

job = Blueprint('job', __name__, url_prefix='/service/<uuid:service_id>/job')

from app.errors import (
    register_errors,
    InvalidRequest
)

register_errors(job)


@job.route('/<job_id>', methods=['GET'])
def get_job_by_service_and_job_id(service_id, job_id):
    job = dao_get_job_by_service_id_and_job_id(service_id, job_id)
    data = job_schema.dump(job).data
    return jsonify(data=data)


@job.route('', methods=['GET'])
def get_jobs_by_service(service_id):
    if request.args.get('limit_days'):
        try:
            limit_days = int(request.args['limit_days'])
        except ValueError as e:
            errors = {'limit_days': ['{} is not an integer'.format(request.args['limit_days'])]}
            raise InvalidRequest(errors, status_code=400)
    else:
        limit_days = None

    jobs = dao_get_jobs_by_service_id(service_id, limit_days)
    data = job_schema.dump(jobs, many=True).data
    return jsonify(data=data)


@job.route('', methods=['POST'])
def create_job(service_id):
    dao_fetch_service_by_id(service_id)

    data = request.get_json()
    data.update({
        "service": service_id
    })
    template = dao_get_template_by_id(data['template'])

    errors = unarchived_template_schema.validate({'archived': template.archived})

    if errors:
        raise InvalidRequest(errors, status_code=400)

    data.update({"template_version": template.version})
    job = job_schema.load(data).data
    dao_create_job(job)
    process_job.apply_async([str(job.id)], queue="process-job")
    return jsonify(data=job_schema.dump(job).data), 201
