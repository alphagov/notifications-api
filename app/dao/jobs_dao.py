from datetime import date, timedelta

from sqlalchemy import desc
from app import db
from app.models import Job


def dao_get_job_by_service_id_and_job_id(service_id, job_id):
    return Job.query.filter_by(service_id=service_id, id=job_id).one()


def dao_get_jobs_by_service_id(service_id, limit_days=None):
    query_filter = [Job.service_id == service_id]
    if limit_days is not None:
        query_filter.append(Job.created_at >= _days_ago(limit_days))
    return Job.query.filter(*query_filter).order_by(desc(Job.created_at)).all()


def dao_get_job_by_id(job_id):
    return Job.query.filter_by(id=job_id).one()


def dao_create_job(job):
    db.session.add(job)
    db.session.commit()


def dao_update_job(job):
    db.session.add(job)
    db.session.commit()


def _days_ago(number_of_days):
    return date.today() - timedelta(days=number_of_days)
