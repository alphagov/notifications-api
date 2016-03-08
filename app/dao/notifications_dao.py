from flask import current_app
from app import db
from app.models import Notification, Job, ServiceNotificationStats, TEMPLATE_TYPE_SMS, TEMPLATE_TYPE_EMAIL
from sqlalchemy import desc
from datetime import datetime


def dao_create_notification(notification, notification_type):
    try:
        if notification.job_id:
            update_job_sent_count(notification)

        day = datetime.utcnow().strftime('%Y-%m-%d')

        if notification_type == TEMPLATE_TYPE_SMS:
            update = {
                ServiceNotificationStats.sms_requested: ServiceNotificationStats.sms_requested + 1
            }
        else:
            update = {
                ServiceNotificationStats.emails_requested: ServiceNotificationStats.emails_requested + 1
            }

        result = db.session.query(ServiceNotificationStats).filter_by(
            day=day,
            service_id=notification.service_id
        ).update(update)

        if result == 0:
            stats = ServiceNotificationStats(
                day=day,
                service_id=notification.service_id,
                sms_requested=1 if notification_type == TEMPLATE_TYPE_SMS else 0,
                emails_requested=1 if notification_type == TEMPLATE_TYPE_EMAIL else 0
            )
            db.session.add(stats)
        db.session.add(notification)
        db.session.commit()
    except:
        db.session.rollback()
        raise


def update_job_sent_count(notification):
    db.session.query(Job).filter_by(
        id=notification.job_id
    ).update({
        Job.notifications_sent: Job.notifications_sent + 1,
        Job.updated_at: datetime.utcnow()
    })


def dao_update_notification(notification):
    db.session.add(notification)
    db.session.commit()


def get_notification_for_job(service_id, job_id, notification_id):
    return Notification.query.filter_by(service_id=service_id, job_id=job_id, id=notification_id).one()


def get_notifications_for_job(service_id, job_id, page=1):
    query = Notification.query.filter_by(service_id=service_id, job_id=job_id) \
        .order_by(desc(Notification.created_at)) \
        .paginate(
        page=page,
        per_page=current_app.config['PAGE_SIZE']
    )
    return query


def get_notification(service_id, notification_id):
    return Notification.query.filter_by(service_id=service_id, id=notification_id).one()


def get_notifications_for_service(service_id, page=1):
    query = Notification.query.filter_by(service_id=service_id).order_by(desc(Notification.created_at)).paginate(
        page=page,
        per_page=current_app.config['PAGE_SIZE']
    )
    return query
