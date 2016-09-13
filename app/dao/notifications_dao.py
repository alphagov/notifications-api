import uuid
from datetime import (
    datetime,
    timedelta,
    date
)

from flask import current_app
from werkzeug.datastructures import MultiDict
from sqlalchemy import (desc, func, or_, and_, asc)
from sqlalchemy.orm import joinedload

from app import db
from app.dao import days_ago
from app.models import (
    Service,
    Notification,
    NotificationHistory,
    NotificationStatistics,
    Template,
    NOTIFICATION_CREATED,
    NOTIFICATION_SENDING,
    NOTIFICATION_PENDING,
    NOTIFICATION_TEMPORARY_FAILURE)

from app.dao.dao_utils import transactional
from app.statsd_decorators import statsd


def dao_get_notification_statistics_for_service_and_day(service_id, day):
    # only used by stat-updating code in tasks.py
    return NotificationStatistics.query.filter_by(
        service_id=service_id,
        day=day
    ).order_by(desc(NotificationStatistics.day)).first()


@statsd(namespace="dao")
def dao_get_potential_notification_statistics_for_day(day):
    all_services = db.session.query(
        Service.id,
        NotificationStatistics
    ).outerjoin(
        NotificationStatistics,
        and_(
            Service.id == NotificationStatistics.service_id,
            or_(
                NotificationStatistics.day == day,
                NotificationStatistics.day == None  # noqa
            )
        )
    ).order_by(
        asc(Service.created_at)
    )

    notification_statistics = []
    for service_notification_stats_pair in all_services:
        if service_notification_stats_pair.NotificationStatistics:
            notification_statistics.append(
                service_notification_stats_pair.NotificationStatistics
            )
        else:
            notification_statistics.append(
                create_notification_statistics_dict(
                    service_notification_stats_pair,
                    day
                )
            )
    return notification_statistics


def create_notification_statistics_dict(service_id, day):
    return {
        'id': None,
        'emails_requested': 0,
        'emails_delivered': 0,
        'emails_failed': 0,
        'sms_requested': 0,
        'sms_delivered': 0,
        'sms_failed': 0,
        'day': day.isoformat(),
        'service': service_id
    }


@statsd(namespace="dao")
def dao_get_template_usage(service_id, limit_days=None):
    table = NotificationHistory

    if limit_days and limit_days <= 7:  # can get this data from notifications table
        table = Notification

    query = db.session.query(
        func.count(table.template_id).label('count'),
        table.template_id,
        Template.name,
        Template.template_type
    )

    query_filter = [table.service_id == service_id]
    if limit_days is not None:
        query_filter.append(table.created_at >= days_ago(limit_days))

    return query.filter(*query_filter) \
        .join(Template) \
        .group_by(table.template_id, Template.name, Template.template_type) \
        .order_by(asc(Template.name)) \
        .all()


@statsd(namespace="dao")
def dao_get_last_template_usage(template_id):
    return NotificationHistory.query.filter(NotificationHistory.template_id == template_id) \
        .join(Template) \
        .order_by(desc(NotificationHistory.created_at)) \
        .first()


@statsd(namespace="dao")
@transactional
def dao_create_notification(notification):
    if not notification.id:
        # need to populate defaulted fields before we create the notification history object
        notification.id = uuid.uuid4()
    if not notification.status:
        notification.status = 'created'

    notification_history = NotificationHistory.from_notification(notification)
    db.session.add(notification)
    db.session.add(notification_history)


def _decide_permanent_temporary_failure(current_status, status):
    # Firetext will send pending, then send either succes or fail.
    # If we go from pending to delivered we need to set failure type as temporary-failure
    if current_status == 'pending':
        if status == 'permanent-failure':
            status = 'temporary-failure'
    return status


def _update_notification_status(notification, status):
    status = _decide_permanent_temporary_failure(current_status=notification.status, status=status)
    notification.status = status
    dao_update_notification(notification)
    return True


@statsd(namespace="dao")
@transactional
def update_notification_status_by_id(notification_id, status):
    notification = Notification.query.with_lockmode("update").filter(
        Notification.id == notification_id,
        or_(Notification.status == 'created',
            Notification.status == 'sending',
            Notification.status == 'pending')).first()

    if not notification:
        return False

    return _update_notification_status(
        notification=notification,
        status=status
    )


@statsd(namespace="dao")
@transactional
def update_notification_status_by_reference(reference, status):
    notification = Notification.query.filter(
        Notification.reference == reference,
        or_(Notification.status == 'sending',
            Notification.status == 'pending')).first()

    if not notification:
        return False

    return _update_notification_status(
        notification=notification,
        status=status
    )


@statsd(namespace="dao")
def dao_update_notification(notification):
    notification.updated_at = datetime.utcnow()
    notification_history = NotificationHistory.query.get(notification.id)
    notification_history.update_from_notification(notification)
    db.session.add(notification)
    db.session.commit()


@statsd(namespace="dao")
def get_notification_for_job(service_id, job_id, notification_id):
    return Notification.query.filter_by(service_id=service_id, job_id=job_id, id=notification_id).one()


@statsd(namespace="dao")
def get_notifications_for_job(service_id, job_id, filter_dict=None, page=1, page_size=None):
    if page_size is None:
        page_size = current_app.config['PAGE_SIZE']
    query = Notification.query.filter_by(service_id=service_id, job_id=job_id)
    query = _filter_query(query, filter_dict)
    return query.order_by(asc(Notification.job_row_number)).paginate(
        page=page,
        per_page=page_size
    )


@statsd(namespace="dao")
def get_notification_with_personalisation(service_id, notification_id, key_type):
    filter_dict = {'service_id': service_id, 'id': notification_id}
    if key_type:
        filter_dict['key_type'] = key_type

    return Notification.query.filter_by(**filter_dict).options(joinedload('template_history')).one()


@statsd(namespace="dao")
def get_notification_by_id(notification_id):
    return Notification.query.filter_by(id=notification_id).first()


def get_notifications(filter_dict=None):
    return _filter_query(Notification.query, filter_dict=filter_dict)


@statsd(namespace="dao")
def get_notifications_for_service(service_id,
                                  filter_dict=None,
                                  page=1,
                                  page_size=None,
                                  limit_days=None,
                                  key_type=None,
                                  personalisation=False):
    if page_size is None:
        page_size = current_app.config['PAGE_SIZE']
    filters = [Notification.service_id == service_id]

    if limit_days is not None:
        days_ago = date.today() - timedelta(days=limit_days)
        filters.append(func.date(Notification.created_at) >= days_ago)

    if key_type is not None:
        filters.append(Notification.key_type == key_type)

    query = Notification.query.filter(*filters)
    query = _filter_query(query, filter_dict)
    if personalisation:
        query = query.options(
            joinedload('template_history')
        )
    return query.order_by(desc(Notification.created_at)).paginate(
        page=page,
        per_page=page_size
    )


def _filter_query(query, filter_dict=None):
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


@statsd(namespace="dao")
def delete_notifications_created_more_than_a_week_ago(status):
    seven_days_ago = date.today() - timedelta(days=7)
    deleted = db.session.query(Notification).filter(
        func.date(Notification.created_at) < seven_days_ago,
        Notification.status == status
    ).delete(synchronize_session='fetch')
    db.session.commit()
    return deleted


@statsd(namespace="dao")
@transactional
def dao_delete_notifications_and_history_by_id(notification_id):
    db.session.query(Notification).filter(
        Notification.id == notification_id
    ).delete(synchronize_session='fetch')
    db.session.query(NotificationHistory).filter(
        NotificationHistory.id == notification_id
    ).delete(synchronize_session='fetch')


def dao_timeout_notifications(timeout_period_in_seconds):
    # update all notifications that are older that the timeout_period_in_seconds
    #  with a status of created|sending|pending
    updated = db.session.query(Notification). \
        filter(Notification.created_at < (datetime.utcnow() - timedelta(seconds=timeout_period_in_seconds))). \
        filter(Notification.status.in_([NOTIFICATION_CREATED, NOTIFICATION_SENDING, NOTIFICATION_PENDING])). \
        update({'status': NOTIFICATION_TEMPORARY_FAILURE}, synchronize_session=False)
    db.session.query(NotificationHistory). \
        filter(NotificationHistory.created_at < (datetime.utcnow() - timedelta(seconds=timeout_period_in_seconds))). \
        filter(NotificationHistory.status.in_([NOTIFICATION_CREATED, NOTIFICATION_SENDING, NOTIFICATION_PENDING])). \
        update({'status': NOTIFICATION_TEMPORARY_FAILURE}, synchronize_session=False)
    db.session.commit()
    return updated
