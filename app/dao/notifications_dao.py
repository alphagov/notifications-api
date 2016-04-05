from sqlalchemy import (
    desc,
    func
)

from datetime import (
    datetime,
    timedelta,
    date
)

from flask import current_app
from werkzeug.datastructures import MultiDict

from app import db
from app.models import (
    Notification,
    Job,
    NotificationStatistics,
    TemplateStatistics,
    TEMPLATE_TYPE_SMS,
    TEMPLATE_TYPE_EMAIL,
    Template
)

from app.clients import (
    STATISTICS_FAILURE,
    STATISTICS_DELIVERED,
    STATISTICS_REQUESTED
)

from functools import wraps


def transactional(func):
    @wraps(func)
    def commit_or_rollback(*args, **kwargs):
        from flask import current_app
        from app import db
        try:
            func(*args, **kwargs)
            db.session.commit()
        except Exception as e:
            current_app.logger.error(e)
            db.session.rollback()
            raise
    return commit_or_rollback


def dao_get_notification_statistics_for_service(service_id):
    return NotificationStatistics.query.filter_by(
        service_id=service_id
    ).order_by(desc(NotificationStatistics.day)).all()


def dao_get_notification_statistics_for_service_and_day(service_id, day):
    return NotificationStatistics.query.filter_by(
        service_id=service_id,
        day=day
    ).order_by(desc(NotificationStatistics.day)).first()


def dao_get_template_statistics_for_service(service_id, limit_days=None):
    filter = [TemplateStatistics.service_id == service_id]
    if limit_days:
        latest_stat = TemplateStatistics.query.filter_by(service_id=service_id).order_by(
            desc(TemplateStatistics.day)).limit(1).first()
        if latest_stat:
            last_date_to_fetch = latest_stat.day - timedelta(days=limit_days)
        else:
            last_date_to_fetch = date.today() - timedelta(days=limit_days)
        filter.append(TemplateStatistics.day > last_date_to_fetch)
    return TemplateStatistics.query.filter(*filter).order_by(
        desc(TemplateStatistics.day)).join(Template).order_by(func.lower(Template.name)).all()


@transactional
def dao_create_notification(notification, notification_type):
    if notification.job_id:
        db.session.query(Job).filter_by(
            id=notification.job_id
        ).update({
            Job.notifications_sent: Job.notifications_sent + 1,
            Job.updated_at: datetime.utcnow()
        })

    update_count = db.session.query(NotificationStatistics).filter_by(
        day=notification.created_at.strftime('%Y-%m-%d'),
        service_id=notification.service_id
    ).update(update_query(notification_type, 'requested'))

    if update_count == 0:
        stats = NotificationStatistics(
            day=notification.created_at.strftime('%Y-%m-%d'),
            service_id=notification.service_id,
            sms_requested=1 if notification_type == TEMPLATE_TYPE_SMS else 0,
            emails_requested=1 if notification_type == TEMPLATE_TYPE_EMAIL else 0
        )
        db.session.add(stats)

    update_count = db.session.query(TemplateStatistics).filter_by(
        day=date.today(),
        service_id=notification.service_id,
        template_id=notification.template_id
    ).update({'usage_count': TemplateStatistics.usage_count + 1})

    if update_count == 0:
        template_stats = TemplateStatistics(template_id=notification.template_id,
                                            service_id=notification.service_id)
        db.session.add(template_stats)

    db.session.add(notification)


def update_query(notification_type, status):
    mapping = {
        TEMPLATE_TYPE_SMS: {
            STATISTICS_REQUESTED: NotificationStatistics.sms_requested,
            STATISTICS_DELIVERED: NotificationStatistics.sms_delivered,
            STATISTICS_FAILURE: NotificationStatistics.sms_error
        },
        TEMPLATE_TYPE_EMAIL: {
            STATISTICS_REQUESTED: NotificationStatistics.emails_requested,
            STATISTICS_DELIVERED: NotificationStatistics.emails_delivered,
            STATISTICS_FAILURE: NotificationStatistics.emails_error
        }
    }
    return {
        mapping[notification_type][status]: mapping[notification_type][status] + 1
    }


def dao_update_notification(notification):
    notification.updated_at = datetime.utcnow()
    db.session.add(notification)
    db.session.commit()


def update_notification_status_by_id(notification_id, status, notification_statistics_status):
    count = db.session.query(Notification).filter_by(
        id=notification_id
    ).update({
        Notification.status: status
    })

    if count == 1 and notification_statistics_status:
        notification = Notification.query.get(notification_id)

        db.session.query(NotificationStatistics).filter_by(
            day=notification.created_at.strftime('%Y-%m-%d'),
            service_id=notification.service_id
        ).update(
            update_query(notification.template.template_type, notification_statistics_status)
        )

    db.session.commit()
    return count


def update_notification_status_by_reference(reference, status, notification_statistics_status):
    count = db.session.query(Notification).filter_by(
        reference=reference
    ).update({
        Notification.status: status
    })

    if count == 1:
        notification = Notification.query.filter_by(
            reference=reference
        ).first()

        db.session.query(NotificationStatistics).filter_by(
            day=notification.created_at.strftime('%Y-%m-%d'),
            service_id=notification.service_id
        ).update(
            update_query(notification.template.template_type, notification_statistics_status)
        )

    db.session.commit()
    return count


def update_notification_reference_by_id(id, reference):
    count = db.session.query(Notification).filter_by(
        id=id
    ).update({
        Notification.reference: reference
    })
    db.session.commit()
    return count


def get_notification_for_job(service_id, job_id, notification_id):
    return Notification.query.filter_by(service_id=service_id, job_id=job_id, id=notification_id).one()


def get_notifications_for_job(service_id, job_id, filter_dict=None, page=1):
    query = Notification.query.filter_by(service_id=service_id, job_id=job_id)
    query = filter_query(query, filter_dict)
    pagination = query.order_by(desc(Notification.created_at)).paginate(
        page=page,
        per_page=current_app.config['PAGE_SIZE']
    )
    return pagination


def get_notification(service_id, notification_id):
    return Notification.query.filter_by(service_id=service_id, id=notification_id).one()


def get_notification_by_id(notification_id):
    return Notification.query.filter_by(id=notification_id).first()


def get_notifications_for_service(service_id, filter_dict=None, page=1):
    query = Notification.query.filter_by(service_id=service_id)
    query = filter_query(query, filter_dict)
    pagination = query.order_by(desc(Notification.created_at)).paginate(
        page=page,
        per_page=current_app.config['PAGE_SIZE']
    )
    return pagination


def filter_query(query, filter_dict=None):
    if filter_dict is None:
        filter_dict = MultiDict()
    else:
        filter_dict = MultiDict(filter_dict)
    statuses = filter_dict.getlist('status') if 'status' in filter_dict else None
    if statuses:
        query = query.filter(Notification.status.in_(statuses))
    template_types = filter_dict.getlist('template_type') if 'template_type' in filter_dict else None
    if template_types:
        query = query.join(Template).filter(Template.template_type.in_(template_types))
    return query


def delete_successful_notifications_created_more_than_a_day_ago():
    deleted = db.session.query(Notification).filter(
        Notification.created_at < datetime.utcnow() - timedelta(days=1),
        Notification.status == 'sent'
    ).delete()
    db.session.commit()
    return deleted


def delete_failed_notifications_created_more_than_a_week_ago():
    deleted = db.session.query(Notification).filter(
        Notification.created_at < datetime.utcnow() - timedelta(days=7),
        Notification.status == 'failed'
    ).delete()
    db.session.commit()
    return deleted
