from datetime import datetime

from flask import current_app
from sqlalchemy import func, desc, asc, cast, Date as sql_date

from app import db
from app.dao import days_ago
from app.models import (Job,
                        Notification,
                        NotificationHistory,
                        Template,
                        JOB_STATUS_SCHEDULED,
                        JOB_STATUS_PENDING,
                        LETTER_TYPE, JobStatistics)
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


@statsd(namespace="dao")
def all_notifications_are_created_for_job(job_id):
    query = db.session.query(func.count(Notification.id), Job.id)\
        .join(Job)\
        .filter(Job.id == job_id)\
        .group_by(Job.id)\
        .having(func.count(Notification.id) == Job.notification_count).all()

    return query


@statsd(namespace="dao")
def dao_get_all_notifications_for_job(job_id):
    return db.session.query(Notification).filter(Notification.job_id == job_id).order_by(Notification.created_at).all()


def dao_get_job_by_service_id_and_job_id(service_id, job_id):
    return Job.query.filter_by(service_id=service_id, id=job_id).one()


def dao_get_jobs_by_service_id(service_id, limit_days=None, page=1, page_size=50, statuses=None):
    query_filter = [
        Job.service_id == service_id,
        Job.original_file_name != current_app.config['TEST_MESSAGE_FILENAME']
    ]
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
    job_stats = JobStatistics(
        job_id=job.id,
        updated_at=datetime.utcnow()
    )
    db.session.add(job_stats)
    db.session.add(job)
    db.session.commit()


def dao_update_job(job):
    db.session.add(job)
    db.session.commit()


def dao_update_job_status(job_id, status):
    db.session.query(Job).filter_by(id=job_id).update({'job_status': status})
    db.session.commit()


def dao_get_jobs_older_than_limited_by(older_than=7, limit_days=2):
    return Job.query.filter(
        cast(Job.created_at, sql_date) < days_ago(older_than),
        cast(Job.created_at, sql_date) >= days_ago(older_than + limit_days)
    ).order_by(desc(Job.created_at)).all()


def dao_get_all_letter_jobs():
    return db.session.query(Job).join(Job.template).filter(
        Template.template_type == LETTER_TYPE
    ).order_by(desc(Job.created_at)).all()
