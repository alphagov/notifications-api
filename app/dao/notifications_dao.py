import functools
from datetime import (
    datetime,
    timedelta,
    date
)

from flask import current_app

from notifications_utils.recipients import (
    validate_and_format_phone_number,
    validate_and_format_email_address,
    InvalidPhoneError,
    InvalidEmailError,
)
from werkzeug.datastructures import MultiDict
from sqlalchemy import (desc, func, or_, and_, asc)
from sqlalchemy.orm import joinedload
from notifications_utils.international_billing_rates import INTERNATIONAL_BILLING_RATES

from app import db, create_uuid
from app.dao import days_ago
from app.dao.date_util import get_financial_year
from app.definitions import (
    NOTIFICATION_CREATED,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_SENDING,
    NOTIFICATION_PENDING,
    NOTIFICATION_TECHNICAL_FAILURE,
    NOTIFICATION_TEMPORARY_FAILURE,
    NOTIFICATION_PERMANENT_FAILURE,
    KEY_TYPE_NORMAL, KEY_TYPE_TEST,
    LETTER_TYPE,
    NOTIFICATION_SENT
)

from app.models import (
    Service,
    Notification,
    NotificationHistory,
    NotificationStatistics,
    Template,
    ScheduledNotification
)

from app.dao.dao_utils import transactional
from app.statsd_decorators import statsd
from app.utils import get_london_month_from_utc_column


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

    query_filter = [table.service_id == service_id, table.key_type != KEY_TYPE_TEST]
    if limit_days is not None:
        query_filter.append(table.created_at >= days_ago(limit_days))

    notifications_aggregate_query = db.session.query(
        func.count().label('count'),
        table.template_id
    ).filter(
        *query_filter
    ).group_by(
        table.template_id
    ).subquery()

    query = db.session.query(
        Template.id.label('template_id'),
        Template.name,
        Template.template_type,
        notifications_aggregate_query.c.count
    ).join(
        notifications_aggregate_query,
        notifications_aggregate_query.c.template_id == Template.id
    ).order_by(Template.name)

    return query.all()


@statsd(namespace="dao")
def dao_get_last_template_usage(template_id):
    return NotificationHistory.query.filter(
        NotificationHistory.template_id == template_id,
        NotificationHistory.key_type != KEY_TYPE_TEST
    ).order_by(
        desc(NotificationHistory.created_at)
    ).first()


@statsd(namespace="dao")
@transactional
def dao_create_notification(notification):
    if not notification.id:
        # need to populate defaulted fields before we create the notification history object
        notification.id = create_uuid()
    if not notification.status:
        notification.status = NOTIFICATION_CREATED

    db.session.add(notification)
    if _should_record_notification_in_history_table(notification):
        db.session.add(NotificationHistory.from_original(notification))


def _should_record_notification_in_history_table(notification):
    if notification.api_key_id and notification.key_type == KEY_TYPE_TEST:
        return False
    if notification.service.research_mode:
        return False
    return True


def _decide_permanent_temporary_failure(current_status, status):
    # Firetext will send pending, then send either succes or fail.
    # If we go from pending to delivered we need to set failure type as temporary-failure
    if current_status == NOTIFICATION_PENDING and status == NOTIFICATION_PERMANENT_FAILURE:
        status = NOTIFICATION_TEMPORARY_FAILURE
    return status


def country_records_delivery(phone_prefix):
    return INTERNATIONAL_BILLING_RATES[phone_prefix]['attributes']['dlr'].lower() == 'yes'


def _update_notification_status(notification, status):
    status = _decide_permanent_temporary_failure(current_status=notification.status, status=status)
    notification.status = status
    dao_update_notification(notification)
    return notification


@statsd(namespace="dao")
@transactional
def update_notification_status_by_id(notification_id, status):
    notification = Notification.query.with_lockmode("update").filter(
        Notification.id == notification_id,
        or_(
            Notification.status == NOTIFICATION_CREATED,
            Notification.status == NOTIFICATION_SENDING,
            Notification.status == NOTIFICATION_PENDING,
            Notification.status == NOTIFICATION_SENT
        )).first()

    if not notification:
        return None

    if notification.international and not country_records_delivery(notification.phone_prefix):
        return None

    return _update_notification_status(
        notification=notification,
        status=status
    )


@statsd(namespace="dao")
@transactional
def update_notification_status_by_reference(reference, status):
    notification = Notification.query.filter(
        Notification.reference == reference,
        or_(
            Notification.status == NOTIFICATION_SENDING,
            Notification.status == NOTIFICATION_PENDING,
            Notification.status == NOTIFICATION_SENT
        )).first()

    if not notification or notification.status == NOTIFICATION_SENT:
        return None

    return _update_notification_status(
        notification=notification,
        status=status
    )


@statsd(namespace="dao")
def dao_update_notification(notification):
    notification.updated_at = datetime.utcnow()
    db.session.add(notification)
    if _should_record_notification_in_history_table(notification):
        notification_history = NotificationHistory.query.get(notification.id)
        notification_history.update_from_original(notification)
        db.session.add(notification_history)
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
def get_notification_billable_unit_count_per_month(service_id, year):
    month = get_london_month_from_utc_column(NotificationHistory.created_at)

    start_date, end_date = get_financial_year(year)
    notifications = db.session.query(
        month,
        func.sum(NotificationHistory.billable_units)
    ).filter(
        NotificationHistory.billable_units != 0,
        NotificationHistory.service_id == service_id,
        NotificationHistory.created_at.between(start_date, end_date)
    ).group_by(
        month
    ).order_by(
        month
    ).all()

    return [(datetime.strftime(x[0], "%B"), x[1]) for x in notifications]


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
def get_notifications_for_service(
    service_id,
    filter_dict=None,
    page=1,
    page_size=None,
    limit_days=None,
    key_type=None,
    personalisation=False,
    include_jobs=False,
    include_from_test_key=False,
    older_than=None,
    client_reference=None
):
    if page_size is None:
        page_size = current_app.config['PAGE_SIZE']

    filters = [Notification.service_id == service_id]

    if limit_days is not None:
        days_ago = date.today() - timedelta(days=limit_days)
        filters.append(func.date(Notification.created_at) >= days_ago)

    if older_than is not None:
        older_than_created_at = db.session.query(
            Notification.created_at).filter(Notification.id == older_than).as_scalar()
        filters.append(Notification.created_at < older_than_created_at)

    if not include_jobs or (key_type and key_type != KEY_TYPE_NORMAL):
        filters.append(Notification.job_id.is_(None))

    if key_type is not None:
        filters.append(Notification.key_type == key_type)
    elif not include_from_test_key:
        filters.append(Notification.key_type != KEY_TYPE_TEST)

    if client_reference is not None:
        filters.append(Notification.client_reference == client_reference)

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
        return query

    multidict = MultiDict(filter_dict)

    # filter by status
    statuses = multidict.getlist('status')
    if statuses:
        statuses = Notification.substitute_status(statuses)
        query = query.filter(Notification.status.in_(statuses))

    # filter by template
    template_types = multidict.getlist('template_type')
    if template_types:
        query = query.join(Template).filter(Template.template_type.in_(template_types))

    return query


@statsd(namespace="dao")
def delete_notifications_created_more_than_a_week_ago_by_type(notification_type):
    seven_days_ago = date.today() - timedelta(days=7)
    deleted = db.session.query(Notification).filter(
        func.date(Notification.created_at) < seven_days_ago,
        Notification.notification_type == notification_type,
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


def _timeout_notifications(current_statuses, new_status, timeout_start, updated_at):
    for table in [NotificationHistory, Notification]:
        q = table.query.filter(
            table.created_at < timeout_start,
            table.status.in_(current_statuses),
            table.notification_type != LETTER_TYPE
        )
        last_update_count = q.update({'status': new_status, 'updated_at': updated_at}, synchronize_session=False)
    return last_update_count


def dao_timeout_notifications(timeout_period_in_seconds):
    """
    Timeout SMS and email notifications by the following rules:

    we never sent the notification to the provider for some reason
        created -> technical-failure

    the notification was sent to the provider but there was not a delivery receipt
        sending -> temporary-failure
        pending -> temporary-failure

    Letter notifications are not timed out
    """
    timeout_start = datetime.utcnow() - timedelta(seconds=timeout_period_in_seconds)
    updated_at = datetime.utcnow()

    timeout = functools.partial(_timeout_notifications, timeout_start=timeout_start, updated_at=updated_at)
    # Notifications still in created status are marked with a technical-failure:
    updated = timeout([NOTIFICATION_CREATED], NOTIFICATION_TECHNICAL_FAILURE)

    # Notifications still in sending or pending status are marked with a temporary-failure:
    updated += timeout([NOTIFICATION_SENDING, NOTIFICATION_PENDING], NOTIFICATION_TEMPORARY_FAILURE)

    db.session.commit()

    return updated


def get_total_sent_notifications_in_date_range(start_date, end_date, notification_type):
    result = db.session.query(
        func.count(NotificationHistory.id).label('count')
    ).filter(
        NotificationHistory.key_type != KEY_TYPE_TEST,
        NotificationHistory.created_at >= start_date,
        NotificationHistory.created_at <= end_date,
        NotificationHistory.notification_type == notification_type
    ).scalar()

    return result or 0


def is_delivery_slow_for_provider(
    sent_at,
    provider,
    threshold,
    delivery_time,
    service_id,
    template_id
):
    count = db.session.query(Notification).filter(
        Notification.service_id == service_id,
        Notification.template_id == template_id,
        Notification.sent_at >= sent_at,
        Notification.status == NOTIFICATION_DELIVERED,
        Notification.sent_by == provider,
        (Notification.updated_at - Notification.sent_at) >= delivery_time,
    ).count()
    return count >= threshold


@statsd(namespace="dao")
@transactional
def dao_update_notifications_sent_to_dvla(job_id, provider):
    now = datetime.utcnow()
    updated_count = db.session.query(
        Notification).filter(Notification.job_id == job_id).update(
        {'status': NOTIFICATION_SENDING, "sent_by": provider, "sent_at": now})

    db.session.query(
        NotificationHistory).filter(NotificationHistory.job_id == job_id).update(
        {'status': NOTIFICATION_SENDING, "sent_by": provider, "sent_at": now, "updated_at": now})

    return updated_count


@statsd(namespace="dao")
def dao_get_notifications_by_to_field(service_id, search_term, statuses=None):
    try:
        normalised = validate_and_format_phone_number(search_term)
    except InvalidPhoneError:
        try:
            normalised = validate_and_format_email_address(search_term)
        except InvalidEmailError:
            normalised = search_term

    filters = [
        Notification.service_id == service_id,
        Notification.normalised_to == normalised
    ]

    if statuses:
        filters.append(Notification.status.in_(statuses))

    results = db.session.query(Notification).filter(*filters).all()
    return results


@statsd(namespace="dao")
def dao_created_scheduled_notification(scheduled_notification):
    db.session.add(scheduled_notification)
    db.session.commit()


@statsd(namespace="dao")
def dao_get_scheduled_notifications():
    notifications = Notification.query.join(
        ScheduledNotification
    ).filter(
        ScheduledNotification.scheduled_for < datetime.utcnow(),
        ScheduledNotification.pending).all()

    return notifications


def set_scheduled_notification_to_processed(notification_id):
    db.session.query(ScheduledNotification).filter(
        ScheduledNotification.notification_id == notification_id
    ).update(
        {'pending': False}
    )
    db.session.commit()
