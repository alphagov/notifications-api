from flask import current_app
from sqlalchemy import desc, literal

from app import db
from app.models import (
    Job, Notification, Template, LETTER_TYPE, JOB_STATUS_CANCELLED, JOB_STATUS_SCHEDULED,
    NOTIFICATION_CANCELLED
)
from app.utils import midnight_n_days_ago


def dao_get_uploads_by_service_id(service_id, limit_days=None, page=1, page_size=50):
    # Hardcoded filter to exclude cancelled or scheduled jobs
    # for the moment, but we may want to change this method take 'statuses' as a argument in the future
    jobs_query_filter = [
        Job.service_id == service_id,
        Job.original_file_name != current_app.config['TEST_MESSAGE_FILENAME'],
        Job.original_file_name != current_app.config['ONE_OFF_MESSAGE_FILENAME'],
        Job.job_status.notin_([JOB_STATUS_CANCELLED, JOB_STATUS_SCHEDULED])
    ]
    if limit_days is not None:
        jobs_query_filter.append(Job.created_at >= midnight_n_days_ago(limit_days))

    jobs_query = db.session.query(
        Job.id,
        Job.original_file_name,
        Job.notification_count,
        Template.template_type,
        Job.created_at.label("created_at"),
        Job.scheduled_for.label("scheduled_for"),
        Job.processing_started.label('processing_started'),
        Job.job_status.label("status"),
        literal('job').label('upload_type')
    ).join(
        Template, Job.template_id == Template.id
    ).filter(
        *jobs_query_filter
    )

    letters_query_filter = [
        Notification.service_id == service_id,
        Notification.notification_type == LETTER_TYPE,
        Notification.api_key_id == None,  # noqa
        Notification.status != NOTIFICATION_CANCELLED,
        Template.hidden == True,

    ]
    if limit_days is not None:
        letters_query_filter.append(Notification.created_at >= midnight_n_days_ago(limit_days))

    letters_query = db.session.query(
        Notification.id,
        Notification.client_reference.label('original_file_name'),
        literal('1').label('notification_count'),
        literal(None).label('template_type'),
        Notification.created_at.label("created_at"),
        literal(None).label('scheduled_for'),
        # letters don't have a processing_started date but we want created_at to be used for sorting
        Notification.created_at.label('processing_started'),
        Notification.status,
        literal('letter').label('upload_type')
    ).join(
        Template, Notification.template_id == Template.id
    ).filter(
        *letters_query_filter
    )

    return jobs_query.union_all(
        letters_query
    ).order_by(
        desc("processing_started"), desc("created_at")
    ).paginate(page=page, per_page=page_size)
