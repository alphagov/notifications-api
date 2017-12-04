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
from sqlalchemy import (desc, func, or_, asc)
from sqlalchemy.orm import joinedload
from sqlalchemy.sql.expression import case
from sqlalchemy.sql import functions
from notifications_utils.international_billing_rates import INTERNATIONAL_BILLING_RATES

from app import db, create_uuid
from app.dao import days_ago
from app.models import (
    Notification,
    NotificationHistory,
    ScheduledNotification,
    Template,
    TemplateHistory,
    KEY_TYPE_NORMAL,
    KEY_TYPE_TEST,
    LETTER_TYPE,
    NOTIFICATION_CREATED,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_SENDING,
    NOTIFICATION_PENDING,
    NOTIFICATION_TECHNICAL_FAILURE,
    NOTIFICATION_TEMPORARY_FAILURE,
    NOTIFICATION_PERMANENT_FAILURE,
    NOTIFICATION_SENT
)

from app.dao.dao_utils import transactional
from app.statsd_decorators import statsd


@statsd(namespace="dao")
def dao_get_template_usage(service_id, limit_days=None):
    query_filter = []

    table = NotificationHistory

    if limit_days is not None and limit_days <= 7:
        table = Notification

        # only limit days if it's not seven days, as 7 days == the whole of Notifications table.
        if limit_days != 7:
            query_filter.append(table.created_at >= days_ago(limit_days))

    elif limit_days is not None:
        # case where not under 7 days, so using NotificationsHistory so limit allowed
        query_filter.append(table.created_at >= days_ago(limit_days))

    query_filter.append(table.service_id == service_id)
    query_filter.append(table.key_type != KEY_TYPE_TEST)

    # only limit days if it's not seven days, as 7 days == the whole of Notifications table.
    if limit_days is not None and limit_days != 7:
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
    return Notification.query.filter(
        Notification.template_id == template_id,
        Notification.key_type != KEY_TYPE_TEST
    ).order_by(
        desc(Notification.created_at)
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
def get_notification_with_personalisation(service_id, notification_id, key_type):
    filter_dict = {'service_id': service_id, 'id': notification_id}
    if key_type:
        filter_dict['key_type'] = key_type

    return Notification.query.filter_by(**filter_dict).options(joinedload('template')).one()


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
        # we can't say "job_id == None" here, because letters sent via the API still have a job_id :(
        filters.append(Notification.api_key_id != None)  # noqa

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
            joinedload('template')
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
        query = query.join(TemplateHistory).filter(TemplateHistory.template_type.in_(template_types))

    return query


@statsd(namespace="dao")
@transactional
def delete_notifications_created_more_than_a_week_ago_by_type(notification_type):
    seven_days_ago = date.today() - timedelta(days=7)
    deleted = db.session.query(Notification).filter(
        func.date(Notification.created_at) < seven_days_ago,
        Notification.notification_type == notification_type,
    ).delete(synchronize_session='fetch')
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
        last_update_count = q.update(
            {'status': new_status, 'updated_at': updated_at},
            synchronize_session=False
        )
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
def dao_update_notifications_for_job_to_sent_to_dvla(job_id, provider):
    now = datetime.utcnow()
    updated_count = db.session.query(
        Notification).filter(Notification.job_id == job_id).update(
        {'status': NOTIFICATION_SENDING, "sent_by": provider, "sent_at": now})

    db.session.query(
        NotificationHistory).filter(NotificationHistory.job_id == job_id).update(
        {'status': NOTIFICATION_SENDING, "sent_by": provider, "sent_at": now, "updated_at": now})

    return updated_count


@statsd(namespace="dao")
@transactional
def dao_update_notifications_by_reference(references, update_dict):
    updated_count = Notification.query.filter(
        Notification.reference.in_(references)
    ).update(
        update_dict,
        synchronize_session=False
    )

    NotificationHistory.query.filter(
        NotificationHistory.reference.in_(references)
    ).update(
        update_dict,
        synchronize_session=False
    )

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
        Notification.normalised_to == normalised,
        Notification.key_type != KEY_TYPE_TEST,
    ]

    if statuses:
        filters.append(Notification.status.in_(statuses))

    results = db.session.query(Notification).filter(*filters).order_by(desc(Notification.created_at)).all()
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


def dao_get_total_notifications_sent_per_day_for_performance_platform(start_date, end_date):
    """
    SELECT
    count(notification_history),
    coalesce(sum(CASE WHEN sent_at - created_at <= interval '10 seconds' THEN 1 ELSE 0 END), 0)
    FROM notification_history
    WHERE
    created_at > 'START DATE' AND
    created_at < 'END DATE' AND
    api_key_id IS NOT NULL AND
    key_type != 'test' AND
    notification_type != 'letter';
    """
    under_10_secs = NotificationHistory.sent_at - NotificationHistory.created_at <= timedelta(seconds=10)
    sum_column = functions.coalesce(functions.sum(
        case(
            [
                (under_10_secs, 1)
            ],
            else_=0
        )
    ), 0)

    return db.session.query(
        func.count(NotificationHistory.id).label('messages_total'),
        sum_column.label('messages_within_10_secs')
    ).filter(
        NotificationHistory.created_at >= start_date,
        NotificationHistory.created_at < end_date,
        NotificationHistory.api_key_id.isnot(None),
        NotificationHistory.key_type != KEY_TYPE_TEST,
        NotificationHistory.notification_type != LETTER_TYPE
    ).one()


def dao_set_created_live_letter_api_notifications_to_pending():
    """
    Sets all past scheduled jobs to pending, and then returns them for further processing.

    this is used in the run_scheduled_jobs task, so we put a FOR UPDATE lock on the job table for the duration of
    the transaction so that if the task is run more than once concurrently, one task will block the other select
    from completing until it commits.
    """
    notifications = db.session.query(
        Notification
    ).filter(
        Notification.notification_type == LETTER_TYPE,
        Notification.status == NOTIFICATION_CREATED,
        Notification.key_type == KEY_TYPE_NORMAL,
        Notification.api_key != None  # noqa
    ).with_for_update(
    ).all()

    for notification in notifications:
        notification.status = NOTIFICATION_PENDING

    db.session.add_all(notifications)
    db.session.commit()

    return notifications


@statsd(namespace="dao")
def dao_get_last_notification_added_for_job_id(job_id):
    last_notification_added = Notification.query.filter(
        Notification.job_id == job_id
    ).order_by(
        Notification.job_row_number.desc()
    ).first()

    return last_notification_added
