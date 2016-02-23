from app import db
from app.models import Job


def save_job(job, update_dict={}):
    if update_dict:
        update_dict.pop('id', None)
        update_dict.pop('service', None)
        update_dict.pop('template', None)
        Job.query.filter_by(id=job.id).update(update_dict)
    else:
        db.session.add(job)
    db.session.commit()


def get_job(service_id, job_id):
    return Job.query.filter_by(service_id=service_id, id=job_id).first()


def get_jobs_by_service(service_id):
    return Job.query.filter_by(service_id=service_id).all()


def _get_jobs():
    return Job.query.all()
