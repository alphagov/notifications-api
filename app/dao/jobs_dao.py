from datetime import datetime

from sqlalchemy import func, desc, asc, cast, Date as sql_date

from app import db
from app.dao import days_ago
from app.models import Job, NotificationHistory, JOB_STATUS_SCHEDULED, JOB_STATUS_PENDING
from app.statsd_decorators import statsd


@statsd(namespace="dao")
def dao_get_notification_outcomes_for_job(service_id, job_id):
    query = db.session.query(
        func.count(NotificationHistory.status).label('count'),
        NotificationHistory.status.label('status')
    )

    return query \
        .filter(NotificationHistory.service_id == service_id) \
        .filter(NotificationHistory.job_id == job_id)\
        .group_by(NotificationHistory.status) \
        .order_by(asc(NotificationHistory.status)) \
        .all()


def dao_get_job_by_service_id_and_job_id(service_id, job_id):
    return Job.query.filter_by(service_id=service_id, id=job_id).one()


def dao_get_jobs_by_service_id(service_id, limit_days=None, page=1, page_size=50, statuses=None):
    query_filter = [Job.service_id == service_id]
    if limit_days is not None:
        query_filter.append(cast(Job.created_at, sql_date) >= days_ago(limit_days))
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
    db.session.add(job)
    db.session.commit()


def dao_update_job(job):
    db.session.add(job)
    db.session.commit()


def dao_get_jobs_older_than(limit_days):
    return Job.query.filter(
        cast(Job.created_at, sql_date) < days_ago(limit_days)
    ).order_by(desc(Job.created_at)).all()
