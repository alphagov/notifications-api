from flask import (
    Blueprint,
    jsonify,
    request,
    current_app
)

from app.dao.jobs_dao import (
    dao_create_job,
    dao_update_job,
    dao_get_job_by_service_id_and_job_id,
    dao_get_jobs_by_service_id,
    dao_get_future_scheduled_job_by_id_and_service_id,
    dao_get_notification_outcomes_for_job,
    dao_get_job_stats_for_service)

from app.dao.services_dao import (
    dao_fetch_service_by_id
)

from app.dao.templates_dao import (dao_get_template_by_id)
from app.dao.notifications_dao import get_notifications_for_job

from app.schemas import (
    job_schema,
    unarchived_template_schema,
    notifications_filter_schema,
    notification_with_template_schema
)

from app.celery.tasks import process_job

from app.models import JOB_STATUS_SCHEDULED, JOB_STATUS_PENDING, JOB_STATUS_CANCELLED

from app.utils import pagination_links

from app.config import QueueNames

job_blueprint = Blueprint('job', __name__, url_prefix='/service/<uuid:service_id>/job')

from app.errors import (
    register_errors,
    InvalidRequest
)

register_errors(job_blueprint)


@job_blueprint.route('/<job_id>', methods=['GET'])
def get_job_by_service_and_job_id(service_id, job_id):
    job = dao_get_job_by_service_id_and_job_id(service_id, job_id)
    statistics = dao_get_notification_outcomes_for_job(service_id, job_id)
    data = job_schema.dump(job).data

    data['statistics'] = [{'status': statistic[1], 'count': statistic[0]} for statistic in statistics]

    return jsonify(data=data)


@job_blueprint.route('/<job_id>/cancel', methods=['POST'])
def cancel_job(service_id, job_id):
    job = dao_get_future_scheduled_job_by_id_and_service_id(job_id, service_id)
    job.job_status = JOB_STATUS_CANCELLED
    dao_update_job(job)

    return get_job_by_service_and_job_id(service_id, job_id)


@job_blueprint.route('/<job_id>/notifications', methods=['GET'])
def get_all_notifications_for_service_job(service_id, job_id):
    data = notifications_filter_schema.load(request.args).data
    page = data['page'] if 'page' in data else 1
    page_size = data['page_size'] if 'page_size' in data else current_app.config.get('PAGE_SIZE')
    paginated_notifications = get_notifications_for_job(
        service_id,
        job_id,
        filter_dict=data,
        page=page,
        page_size=page_size)

    kwargs = request.args.to_dict()
    kwargs['service_id'] = service_id
    kwargs['job_id'] = job_id

    notifications = None
    if data.get('format_for_csv'):
        notifications = [notification.serialize_for_csv() for notification in paginated_notifications.items]
    else:
        notifications = notification_with_template_schema.dump(paginated_notifications.items, many=True).data

    return jsonify(
        notifications=notifications,
        page_size=page_size,
        total=paginated_notifications.total,
        links=pagination_links(
            paginated_notifications,
            '.get_all_notifications_for_service_job',
            **kwargs
        )
    ), 200


@job_blueprint.route('', methods=['GET'])
def get_jobs_by_service(service_id):
    if request.args.get('limit_days'):
        try:
            limit_days = int(request.args['limit_days'])
        except ValueError:
            errors = {'limit_days': ['{} is not an integer'.format(request.args['limit_days'])]}
            raise InvalidRequest(errors, status_code=400)
    else:
        limit_days = None

    statuses = [x.strip() for x in request.args.get('statuses', '').split(',')]

    page = int(request.args.get('page', 1))
    return jsonify(**get_paginated_jobs(service_id, limit_days, statuses, page))


@job_blueprint.route('/job-stats', methods=['GET'])
def get_jobs_for_service(service_id):
    if request.args.get('limit_days'):
        try:
            limit_days = int(request.args['limit_days'])
        except ValueError:
            errors = {'limit_days': ['{} is not an integer'.format(request.args['limit_days'])]}
            raise InvalidRequest(errors, status_code=400)
    else:
        limit_days = None
    statuses = _parse_statuses(request.args.get('statuses', ''))
    page = int(request.args.get('page', 1))

    pagination = dao_get_job_stats_for_service(service_id=service_id,
                                               page=page,
                                               page_size=current_app.config['PAGE_SIZE'],
                                               limit_days=limit_days,
                                               statuses=statuses)
    return jsonify({
        'data': [_serialize_job_stats(x) for x in pagination.items],
        'page_size': pagination.per_page,
        'total': pagination.total,
        'links': pagination_links(
            pagination,
            '.get_jobs_by_service',
            service_id=service_id
        )
    })


def _parse_statuses(statuses):
    return [x.strip() for x in statuses.split(',')]


def _serialize_job_stats(stat):
    return {
        "job_id": stat.job_id,
        "original_file_name": stat.original_file_name,
        "created_at": stat.created_at,
        "scheduled_for": stat.scheduled_for,
        "sent": stat.sent,
        "delivered": stat.delivered,
        "failed": stat.failed
    }


@job_blueprint.route('', methods=['POST'])
def create_job(service_id):
    service = dao_fetch_service_by_id(service_id)
    if not service.active:
        raise InvalidRequest("Create job is not allowed: service is inactive ", 403)

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

    if job.scheduled_for:
        job.job_status = JOB_STATUS_SCHEDULED

    dao_create_job(job)

    if job.job_status == JOB_STATUS_PENDING:
        process_job.apply_async([str(job.id)], queue=QueueNames.JOBS)

    job_json = job_schema.dump(job).data
    job_json['statistics'] = []

    return jsonify(data=job_json), 201


def get_paginated_jobs(service_id, limit_days, statuses, page):
    pagination = dao_get_jobs_by_service_id(
        service_id,
        limit_days=limit_days,
        page=page,
        page_size=current_app.config['PAGE_SIZE'],
        statuses=statuses
    )
    data = job_schema.dump(pagination.items, many=True).data
    for job_data in data:
        statistics = dao_get_notification_outcomes_for_job(service_id, job_data['id'])
        job_data['statistics'] = [{'status': statistic[1], 'count': statistic[0]} for statistic in statistics]

    return {
        'data': data,
        'page_size': pagination.per_page,
        'total': pagination.total,
        'links': pagination_links(
            pagination,
            '.get_jobs_by_service',
            service_id=service_id
        )
    }
