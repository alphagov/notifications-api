from flask import (
    Blueprint,
    jsonify,
    request,
    current_app
)

from app.dao.fact_notification_status_dao import fetch_notification_statuses_for_job
from app.dao.jobs_dao import (
    dao_get_notification_outcomes_for_job
)
from app.dao.uploads_dao import dao_get_uploads_by_service_id
from app.errors import (
    register_errors,
)
from app.utils import pagination_links, midnight_n_days_ago

upload_blueprint = Blueprint('upload', __name__, url_prefix='/service/<uuid:service_id>/upload')

register_errors(upload_blueprint)


@upload_blueprint.route('', methods=['GET'])
def get_uploads_by_service(service_id):
    return jsonify(**get_paginated_uploads(service_id,
                                           request.args.get('limit_days', type=int),
                                           request.args.get('page', type=int)))


def get_paginated_uploads(service_id, limit_days, page):
    pagination = dao_get_uploads_by_service_id(
        service_id,
        limit_days=limit_days,
        page=page,
        page_size=current_app.config['PAGE_SIZE']
    )
    uploads = pagination.items
    data = []
    for upload in uploads:
        upload_dict = {
            'id': upload.id,
            'original_file_name': upload.original_file_name,
            'notification_count': upload.notification_count,
            'created_at': upload.scheduled_for.strftime(
                "%Y-%m-%d %H:%M:%S") if upload.scheduled_for else upload.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            'upload_type': upload.upload_type,
            'template_type': None,
            'recipient': upload.recipient,
        }
        if upload.upload_type == 'job':
            start = upload.processing_started

            if start is None:
                statistics = []
            elif start.replace(tzinfo=None) < midnight_n_days_ago(3):
                # ft_notification_status table
                statistics = fetch_notification_statuses_for_job(upload.id)
            else:
                # notifications table
                statistics = dao_get_notification_outcomes_for_job(service_id, upload.id)
            upload_dict['statistics'] = [{'status': statistic.status, 'count': statistic.count} for statistic in
                                         statistics]
            upload_dict['template_type'] = upload.template_type
        else:
            upload_dict['statistics'] = [{'status': upload.status, 'count': 1}]
        data.append(upload_dict)

    return {
        'data': data,
        'page_size': pagination.per_page,
        'total': pagination.total,
        'links': pagination_links(
            pagination,
            '.get_uploads_by_service',
            service_id=service_id
        )
    }
