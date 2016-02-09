from app import db
from app.models import Notification


def save_notification(notification, update_dict={}):
    if update_dict:
        update_dict.pop('id', None)
        update_dict.pop('job', None)
        update_dict.pop('service', None)
        update_dict.pop('template', None)
        Notification.query.filter_by(id=notification.id).update(update_dict)
    else:
        db.session.add(notification)
    db.session.commit()


def get_notification(job_id, notification_id):
    return Notification.query.filter_by(job_id=job_id, id=notification_id).one()


def get_notifications_by_job(job_id):
    return Notification.query.filter_by(job_id=job_id).all()
