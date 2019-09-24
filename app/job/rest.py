import dateutil
from flask import (
    Blueprint,
    jsonify,
    request,
    current_app
)

from app.aws.s3 import get_job_metadata_from_s3
from app.dao.jobs_dao import (
    dao_create_job,
    dao_update_job,
    dao_get_job_by_service_id_and_job_id,
    dao_get_jobs_by_service_id,
    dao_get_future_scheduled_job_by_id_and_service_id,
    dao_get_notification_outcomes_for_job,
    dao_cancel_letter_job,
    can_letter_job_be_cancelled
)
from app.dao.fact_notification_status_dao import fetch_notification_statuses_for_job
from app.dao.services_dao import dao_fetch_service_by_id
from app.dao.templates_dao import dao_get_template_by_id
from app.dao.notifications_dao import dao_get_notification_count_for_job_id, get_notifications_for_job
from app.schemas import (
    job_schema,
    unarchived_template_schema,
    notifications_filter_schema,
    notification_with_template_schema
)
from app.celery.tasks import process_job
from app.models import JOB_STATUS_SCHEDULED, JOB_STATUS_PENDING, JOB_STATUS_CANCELLED, LETTER_TYPE
from app.utils import pagination_links, midnight_n_days_ago
from app.config import QueueNames
from app.errors import (
    register_errors,
    InvalidRequest
)


job_blueprint = Blueprint('job', __name__, url_prefix='/service/<uuid:service_id>/job')


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


@job_blueprint.route('/<job_id>/cancel-letter-job', methods=['POST'])
def cancel_letter_job(service_id, job_id):
    job = dao_get_job_by_service_id_and_job_id(service_id, job_id)
    can_we_cancel, errors = can_letter_job_be_cancelled(job)
    if can_we_cancel:
        data = dao_cancel_letter_job(job)
        return jsonify(data), 200
    else:
        return jsonify(message=errors), 400


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


@job_blueprint.route('/<job_id>/notification_count', methods=['GET'])
def get_notification_count_for_job_id(service_id, job_id):
    count = dao_get_notification_count_for_job_id(job_id)
    return jsonify(
        count=count
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


@job_blueprint.route('', methods=['POST'])
def create_job(service_id):
    service = dao_fetch_service_by_id(service_id)
    if not service.active:
        raise InvalidRequest("Create job is not allowed: service is inactive ", 403)

    data = request.get_json()

    data.update({
        "service": service_id
    })
    try:
        data.update(
            **get_job_metadata_from_s3(service_id, data['id'])
        )
    except KeyError:
        raise InvalidRequest({'id': ['Missing data for required field.']}, status_code=400)

    data['template'] = data.pop('template_id')
    template = dao_get_template_by_id(data['template'])

    if template.template_type == LETTER_TYPE and service.restricted:
        raise InvalidRequest("Create letter job is not allowed for service in trial mode ", 403)

    if data.get('valid') != 'True':
        raise InvalidRequest("File is not valid, can't create job", 400)

    errors = unarchived_template_schema.validate({'archived': template.archived})

    if errors:
        raise InvalidRequest(errors, status_code=400)

    data.update({"template_version": template.version})

    job = job_schema.load(data).data

    if job.scheduled_for:
        job.job_status = JOB_STATUS_SCHEDULED

    dao_create_job(job)

    sender_id = data.get('sender_id')

    if job.job_status == JOB_STATUS_PENDING:
        process_job.apply_async([str(job.id)], {'sender_id': sender_id}, queue=QueueNames.JOBS)

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
        start = job_data['processing_started']
        start = dateutil.parser.parse(start).replace(tzinfo=None) if start else None

        if start is None:
            statistics = []
        elif start.replace(tzinfo=None) < midnight_n_days_ago(3):
            # ft_notification_status table
            statistics = fetch_notification_statuses_for_job(job_data['id'])
        else:
            # notifications table
            statistics = dao_get_notification_outcomes_for_job(service_id, job_data['id'])
        job_data['statistics'] = [{'status': statistic.status, 'count': statistic.count} for statistic in statistics]

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
