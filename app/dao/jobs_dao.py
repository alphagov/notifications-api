import uuid
from datetime import datetime, timedelta

from flask import current_app
from notifications_utils.letter_timings import letter_can_be_cancelled
from notifications_utils.statsd_decorators import statsd
from sqlalchemy import (
    asc,
    desc,
    func,
)

from app import db
from app.dao.dao_utils import transactional
from app.utils import midnight_n_days_ago
from app.models import (
    Job,
    JOB_STATUS_PENDING,
    JOB_STATUS_SCHEDULED,
    LETTER_TYPE,
    Notification,
    Template,
    ServiceDataRetention,
    NOTIFICATION_SENDING,
    NOTIFICATION_CREATED,
    NOTIFICATION_CANCELLED,
    JOB_STATUS_CANCELLED
)


@statsd(namespace="dao")
def dao_get_notification_outcomes_for_job(service_id, job_id):
    return db.session.query(
        func.count(Notification.status).label('count'),
        Notification.status
    ).filter(
        Notification.service_id == service_id,
        Notification.job_id == job_id
    ).group_by(
        Notification.status
    ).all()


def dao_get_job_by_service_id_and_job_id(service_id, job_id):
    return Job.query.filter_by(service_id=service_id, id=job_id).one()


def dao_get_jobs_by_service_id(service_id, limit_days=None, page=1, page_size=50, statuses=None):
    query_filter = [
        Job.service_id == service_id,
        Job.original_file_name != current_app.config['TEST_MESSAGE_FILENAME'],
        Job.original_file_name != current_app.config['ONE_OFF_MESSAGE_FILENAME'],
    ]
    if limit_days is not None:
        query_filter.append(Job.created_at >= midnight_n_days_ago(limit_days))
    if statuses is not None and statuses != ['']:
        query_filter.append(
            Job.job_status.in_(statuses)
        )
    return Job.query \
        .filter(*query_filter) \
        .order_by(Job.processing_started.desc(), Job.created_at.desc()) \
        .paginate(page=page, per_page=page_size)


def dao_get_job_by_id(job_id):
    return Job.query.filter_by(id=job_id).one()


def dao_archive_job(job):
    job.archived = True
    db.session.add(job)
    db.session.commit()


def dao_set_scheduled_jobs_to_pending():
    """
    Sets all past scheduled jobs to pending, and then returns them for further processing.

    this is used in the run_scheduled_jobs task, so we put a FOR UPDATE lock on the job table for the duration of
    the transaction so that if the task is run more than once concurrently, one task will block the other select
    from completing until it commits.
    """
    jobs = Job.query \
        .filter(
            Job.job_status == JOB_STATUS_SCHEDULED,
            Job.scheduled_for < datetime.utcnow()
        ) \
        .order_by(asc(Job.scheduled_for)) \
        .with_for_update() \
        .all()

    for job in jobs:
        job.job_status = JOB_STATUS_PENDING

    db.session.add_all(jobs)
    db.session.commit()

    return jobs


def dao_get_future_scheduled_job_by_id_and_service_id(job_id, service_id):
    return Job.query \
        .filter(
            Job.service_id == service_id,
            Job.id == job_id,
            Job.job_status == JOB_STATUS_SCHEDULED,
            Job.scheduled_for > datetime.utcnow()
        ) \
        .one()


def dao_create_job(job):
    if not job.id:
        job.id = uuid.uuid4()
    db.session.add(job)
    db.session.commit()


def dao_update_job(job):
    db.session.add(job)
    db.session.commit()


def dao_get_jobs_older_than_data_retention(notification_types):
    flexible_data_retention = ServiceDataRetention.query.filter(
        ServiceDataRetention.notification_type.in_(notification_types)
    ).all()
    jobs = []
    today = datetime.utcnow().date()
    for f in flexible_data_retention:
        end_date = today - timedelta(days=f.days_of_retention)

        jobs.extend(Job.query.join(Template).filter(
            Job.created_at < end_date,
            Job.archived == False,  # noqa
            Template.template_type == f.notification_type,
            Job.service_id == f.service_id
        ).order_by(desc(Job.created_at)).all())

    end_date = today - timedelta(days=7)
    for notification_type in notification_types:
        services_with_data_retention = [
            x.service_id for x in flexible_data_retention if x.notification_type == notification_type
        ]
        jobs.extend(Job.query.join(Template).filter(
            Job.created_at < end_date,
            Job.archived == False,  # noqa
            Template.template_type == notification_type,
            Job.service_id.notin_(services_with_data_retention)
        ).order_by(desc(Job.created_at)).all())

    return jobs


@transactional
def dao_cancel_letter_job(job):
    if can_cancel_letter_job(job):
        number_of_notifications_cancelled = Notification.query.filter(
            Notification.job_id == job.id
        ).update({'status': NOTIFICATION_CANCELLED,
                  'updated_at': datetime.utcnow(),
                  'billable_units': 0})
        job.job_status = JOB_STATUS_CANCELLED
        dao_update_job(job)
        return number_of_notifications_cancelled
    else:
        return False


def can_cancel_letter_job(job):
    # assert is a letter job
    # assert job status == finished???
    # Notifications are not in pending-virus-check
    count_notifications = Notification.query.filter(
        Notification.job_id == job.id,
        Notification.status.in_(['created', 'pending-virus-check', 'cancelled'])
    ).count()
    if count_notifications != job.notification_count:
        return False
    return letter_can_be_cancelled(NOTIFICATION_CREATED, job.created_at)



