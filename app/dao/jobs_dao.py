from app import db
from app.models import Job


def save_job(job):
    db.session.add(job)
    db.session.commit()


def get_job_by_id(id):
    return Job.query.get(id)


def get_jobs_by_service(service_id):
    return Job.query.filter_by(service_id=service_id).all()


def get_jobs():
    return Job.query.all()
