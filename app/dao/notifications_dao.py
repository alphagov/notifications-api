from flask import current_app
from app import db
from app.models import Notification, Job, NotificationStatistics, TEMPLATE_TYPE_SMS, TEMPLATE_TYPE_EMAIL
from sqlalchemy import desc
from datetime import datetime


def dao_get_notification_statistics_for_service(service_id):
    return NotificationStatistics.query.filter_by(
        service_id=service_id
    ).order_by(desc(NotificationStatistics.day)).all()


def dao_create_notification(notification, notification_type):
    try:
        if notification.job_id:
            update_job_sent_count(notification)

        if update_notification_stats(notification, notification_type) == 0:
            stats = NotificationStatistics(
                day=notification.created_at.strftime('%Y-%m-%d'),
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


def update_notification_stats(notification, notification_type):
    if notification_type == TEMPLATE_TYPE_SMS:
        update = {
            NotificationStatistics.sms_requested: NotificationStatistics.sms_requested + 1
        }
    else:
        update = {
            NotificationStatistics.emails_requested: NotificationStatistics.emails_requested + 1
        }

    return db.session.query(NotificationStatistics).filter_by(
        day=notification.created_at.strftime('%Y-%m-%d'),
        service_id=notification.service_id
    ).update(update)


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
