from datetime import datetime

from sqlalchemy import func, desc, asc, cast, Date as sql_date

from app import db
from app.dao import days_ago
from app.models import Job, NotificationHistory, JOB_STATUS_SCHEDULED
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


def dao_get_jobs_by_service_id(service_id, limit_days=None, page=1, page_size=50):
    query_filter = [Job.service_id == service_id]
    if limit_days is not None:
        query_filter.append(cast(Job.created_at, sql_date) >= days_ago(limit_days))
    return Job.query \
        .filter(*query_filter) \
        .order_by(desc(Job.created_at)) \
        .paginate(page=page, per_page=page_size)


def dao_get_job_by_id(job_id):
    return Job.query.filter_by(id=job_id).one()


def dao_get_scheduled_jobs():
    return Job.query \
        .filter(
            Job.job_status == JOB_STATUS_SCHEDULED,
            Job.scheduled_for < datetime.utcnow()
        ) \
        .order_by(asc(Job.scheduled_for)) \
        .all()


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
