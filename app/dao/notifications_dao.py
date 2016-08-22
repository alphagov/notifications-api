import uuid
from datetime import (
    datetime,
    timedelta,
    date
)

from flask import current_app
from werkzeug.datastructures import MultiDict
from sqlalchemy import (desc, func, Integer, or_, and_, asc)
from sqlalchemy.sql.expression import cast

from app import db
from app.dao import days_ago
from app.models import (
    Service,
    Notification,
    NotificationHistory,
    Job,
    NotificationStatistics,
    TemplateStatistics,
    SMS_TYPE,
    EMAIL_TYPE,
    Template,
    ProviderStatistics,
    ProviderDetails)
from app.clients import (
    STATISTICS_FAILURE,
    STATISTICS_DELIVERED,
    STATISTICS_REQUESTED
)
from app.dao.dao_utils import transactional
from app.statsd_decorators import statsd


@statsd(namespace="dao")
def dao_get_notification_statistics_for_service(service_id, limit_days=None):
    query_filter = [NotificationStatistics.service_id == service_id]
    if limit_days is not None:
        query_filter.append(NotificationStatistics.day >= days_ago(limit_days))
    return NotificationStatistics.query.filter(
        *query_filter
    ).order_by(
        desc(NotificationStatistics.day)
    ).all()


@statsd(namespace="dao")
def dao_get_notification_statistics_for_service_and_day(service_id, day):
    return NotificationStatistics.query.filter_by(
        service_id=service_id,
        day=day
    ).order_by(desc(NotificationStatistics.day)).first()


@statsd(namespace="dao")
def dao_get_notification_statistics_for_day(day):
    return NotificationStatistics.query.filter_by(day=day).all()


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
def dao_get_7_day_agg_notification_statistics_for_service(service_id,
                                                          date_from,
                                                          week_count=52):
    doy = date_from.timetuple().tm_yday
    return db.session.query(
        cast(func.floor((func.extract('doy', NotificationStatistics.day) - doy) / 7), Integer),
        cast(func.sum(NotificationStatistics.emails_requested), Integer),
        cast(func.sum(NotificationStatistics.emails_delivered), Integer),
        cast(func.sum(NotificationStatistics.emails_failed), Integer),
        cast(func.sum(NotificationStatistics.sms_requested), Integer),
        cast(func.sum(NotificationStatistics.sms_delivered), Integer),
        cast(func.sum(NotificationStatistics.sms_failed), Integer)
    ).filter(
        NotificationStatistics.service_id == service_id
    ).filter(
        NotificationStatistics.day >= date_from
    ).filter(
        NotificationStatistics.day < date_from + timedelta(days=7 * week_count)
    ).group_by(
        func.floor(((func.extract('doy', NotificationStatistics.day) - doy) / 7))
    ).order_by(
        desc(func.floor(((func.extract('doy', NotificationStatistics.day) - doy) / 7)))
    ).limit(
        week_count
    )


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
        .join(Template)\
        .group_by(table.template_id, Template.name, Template.template_type)\
        .order_by(asc(Template.name))\
        .all()


@statsd(namespace="dao")
def dao_get_template_statistics_for_service(service_id, limit_days=None):
    query_filter = [TemplateStatistics.service_id == service_id]
    if limit_days is not None:
        query_filter.append(TemplateStatistics.day >= days_ago(limit_days))
    return TemplateStatistics.query.filter(*query_filter).order_by(
        desc(TemplateStatistics.updated_at)).all()


@statsd(namespace="dao")
def dao_get_template_statistics_for_template(template_id):
    return TemplateStatistics.query.filter(
        TemplateStatistics.template_id == template_id
    ).order_by(
        desc(TemplateStatistics.updated_at)
    ).all()


@statsd(namespace="dao")
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
        day=notification.created_at.date(),
        service_id=notification.service_id
    ).update(_update_notification_stats_query(notification_type, 'requested'))

    if update_count == 0:
        stats = NotificationStatistics(
            day=notification.created_at.date(),
            service_id=notification.service_id,
            sms_requested=1 if notification_type == SMS_TYPE else 0,
            emails_requested=1 if notification_type == EMAIL_TYPE else 0
        )
        db.session.add(stats)

    update_count = db.session.query(TemplateStatistics).filter_by(
        day=date.today(),
        service_id=notification.service_id,
        template_id=notification.template_id
    ).update({'usage_count': TemplateStatistics.usage_count + 1, 'updated_at': datetime.utcnow()})

    if update_count == 0:
        template_stats = TemplateStatistics(template_id=notification.template_id,
                                            service_id=notification.service_id)
        db.session.add(template_stats)

    if not notification.id:
        # need to populate defaulted fields before we create the notification history object
        notification.id = uuid.uuid4()
    if not notification.status:
        notification.status = 'created'

    notification_history = NotificationHistory.from_notification(notification)

    db.session.add(notification)
    db.session.add(notification_history)


def _update_notification_stats_query(notification_type, status):
    mapping = {
        SMS_TYPE: {
            STATISTICS_REQUESTED: NotificationStatistics.sms_requested,
            STATISTICS_DELIVERED: NotificationStatistics.sms_delivered,
            STATISTICS_FAILURE: NotificationStatistics.sms_failed
        },
        EMAIL_TYPE: {
            STATISTICS_REQUESTED: NotificationStatistics.emails_requested,
            STATISTICS_DELIVERED: NotificationStatistics.emails_delivered,
            STATISTICS_FAILURE: NotificationStatistics.emails_failed
        }
    }
    return {
        mapping[notification_type][status]: mapping[notification_type][status] + 1
    }


def _update_statistics(notification, notification_statistics_status):
    if notification.job_id:
        db.session.query(Job).filter_by(
            id=notification.job_id
        ).update(_update_job_stats_query(notification_statistics_status))

    db.session.query(NotificationStatistics).filter_by(
        day=notification.created_at.date(),
        service_id=notification.service_id
    ).update(
        _update_notification_stats_query(notification.notification_type, notification_statistics_status)
    )


def _update_job_stats_query(status):
    mapping = {
        STATISTICS_FAILURE: Job.notifications_failed,
        STATISTICS_DELIVERED: Job.notifications_delivered
    }
    return {mapping[status]: mapping[status] + 1}


def _decide_permanent_temporary_failure(current_status, status):
    # Firetext will send pending, then send either succes or fail.
    # If we go from pending to delivered we need to set failure type as temporary-failure
    if current_status == 'pending':
        if status == 'permanent-failure':
            status = 'temporary-failure'
    return status


def _update_notification_status(notification, status, notification_statistics_status):
    status = _decide_permanent_temporary_failure(current_status=notification.status, status=status)

    if notification_statistics_status:
        _update_statistics(notification, notification_statistics_status)

    notification.status = status
    dao_update_notification(notification)
    return True


@statsd(namespace="dao")
@transactional
def update_notification_status_by_id(notification_id, status, notification_statistics_status=None):
    notification = Notification.query.with_lockmode("update").filter(
        Notification.id == notification_id,
        or_(Notification.status == 'created',
            Notification.status == 'sending',
            Notification.status == 'pending')).first()

    if not notification:
        return False

    return _update_notification_status(
        notification=notification,
        status=status,
        notification_statistics_status=notification_statistics_status
    )


@statsd(namespace="dao")
@transactional
def update_notification_status_by_reference(reference, status, notification_statistics_status):
    notification = Notification.query.filter(Notification.reference == reference,
                                             or_(Notification.status == 'sending',
                                                 Notification.status == 'pending')
                                             ).first()
    if not notification:
        return False

    return _update_notification_status(
        notification=notification,
        status=status,
        notification_statistics_status=notification_statistics_status
    )


@statsd(namespace="dao")
def dao_update_notification(notification):
    notification.updated_at = datetime.utcnow()
    notification_history = NotificationHistory.query.get(notification.id)
    notification_history.update_from_notification(notification)
    db.session.add(notification)
    db.session.commit()


@statsd(namespace="dao")
@transactional
def update_provider_stats(
        id_,
        notification_type,
        provider_name,
        billable_units=1):
    notification = Notification.query.filter(Notification.id == id_).one()
    provider = ProviderDetails.query.filter_by(identifier=provider_name).one()

    update_count = db.session.query(ProviderStatistics).filter_by(
        day=date.today(),
        service_id=notification.service_id,
        provider_id=provider.id
    ).update({'unit_count': ProviderStatistics.unit_count + billable_units})

    if update_count == 0:
        provider_stats = ProviderStatistics(
            day=notification.created_at.date(),
            service_id=notification.service_id,
            provider_id=provider.id,
            unit_count=billable_units
        )

        db.session.add(provider_stats)


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
def get_notification(service_id, notification_id, key_type=None):
    filter_dict = {'service_id': service_id, 'id': notification_id}
    if key_type:
        filter_dict['key_type'] = key_type

    return Notification.query.filter_by(**filter_dict).one()


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
                                  key_type=None):
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
