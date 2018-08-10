import functools
import string
from datetime import (
    datetime,
    timedelta,
    date
)

from flask import current_app

from notifications_utils.recipients import (
    validate_and_format_email_address,
    InvalidEmailError,
    try_validate_and_format_phone_number
)
from notifications_utils.statsd_decorators import statsd
from werkzeug.datastructures import MultiDict
from sqlalchemy import (desc, func, or_, asc)
from sqlalchemy.orm import joinedload
from sqlalchemy.sql.expression import case
from sqlalchemy.sql import functions
from notifications_utils.international_billing_rates import INTERNATIONAL_BILLING_RATES

from app import db, create_uuid
from app.aws.s3 import get_s3_object_by_prefix
from app.letters.utils import LETTERS_PDF_FILE_LOCATION_STRUCTURE
from app.utils import midnight_n_days_ago, escape_special_characters
from app.errors import InvalidRequest
from app.models import (
    Notification,
    NotificationHistory,
    ScheduledNotification,
    Service,
    Template,
    TemplateHistory,
    KEY_TYPE_TEST,
    LETTER_TYPE,
    NOTIFICATION_CREATED,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_SENDING,
    NOTIFICATION_PENDING,
    NOTIFICATION_TECHNICAL_FAILURE,
    NOTIFICATION_TEMPORARY_FAILURE,
    NOTIFICATION_PERMANENT_FAILURE,
    NOTIFICATION_SENT,
    SMS_TYPE,
    EMAIL_TYPE,
    ServiceDataRetention
)

from app.dao.dao_utils import transactional
from app.utils import convert_utc_to_bst, get_london_midnight_in_utc


@statsd(namespace="dao")
def dao_get_template_usage(service_id, day):
    start = get_london_midnight_in_utc(day)
    end = get_london_midnight_in_utc(day + timedelta(days=1))

    notifications_aggregate_query = db.session.query(
        func.count().label('count'),
        Notification.template_id
    ).filter(
        Notification.created_at >= start,
        Notification.created_at < end,
        Notification.service_id == service_id,
        Notification.key_type != KEY_TYPE_TEST,
    ).group_by(
        Notification.template_id
    ).subquery()

    query = db.session.query(
        Template.id,
        Template.name,
        Template.template_type,
        Template.is_precompiled_letter,
        func.coalesce(notifications_aggregate_query.c.count, 0).label('count')
    ).outerjoin(
        notifications_aggregate_query,
        notifications_aggregate_query.c.template_id == Template.id
    ).filter(
        Template.service_id == service_id
    ).order_by(Template.name)

    return query.all()


@statsd(namespace="dao")
def dao_get_last_template_usage(template_id, template_type, service_id):
    # By adding the service_id to the filter the performance of the query is greatly improved.
    # Using a max(Notification.created_at) is better than order by and limit one.
    # But the effort to change the endpoint to return a datetime only is more than the gain.
    return Notification.query.filter(
        Notification.template_id == template_id,
        Notification.key_type != KEY_TYPE_TEST,
        Notification.notification_type == template_type,
        Notification.service_id == service_id
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
    dlr = INTERNATIONAL_BILLING_RATES[phone_prefix]['attributes']['dlr']
    return dlr and dlr.lower() == 'yes'


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
def get_notification_by_id(notification_id, _raise=False):
    if _raise:
        return Notification.query.filter_by(id=notification_id).one()
    else:
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
        client_reference=None,
        include_one_off=True
):
    if page_size is None:
        page_size = current_app.config['PAGE_SIZE']

    filters = [Notification.service_id == service_id]

    if limit_days is not None:
        filters.append(Notification.created_at >= midnight_n_days_ago(limit_days))

    if older_than is not None:
        older_than_created_at = db.session.query(
            Notification.created_at).filter(Notification.id == older_than).as_scalar()
        filters.append(Notification.created_at < older_than_created_at)

    if not include_jobs:
        filters.append(Notification.job_id == None)  # noqa

    if not include_one_off:
        filters.append(Notification.created_by_id == None)  # noqa

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
    flexible_data_retention = ServiceDataRetention.query.filter(
        ServiceDataRetention.notification_type == notification_type
    ).all()
    deleted = 0
    for f in flexible_data_retention:
        days_of_retention = convert_utc_to_bst(datetime.utcnow()).date() - timedelta(days=f.days_of_retention)
        query = db.session.query(Notification).filter(
            func.date(Notification.created_at) < days_of_retention,
            Notification.notification_type == f.notification_type, Notification.service_id == f.service_id)
        if notification_type == LETTER_TYPE:
            _delete_letters_from_s3(query)
        deleted += query.delete(synchronize_session='fetch')

    seven_days_ago = convert_utc_to_bst(datetime.utcnow()).date() - timedelta(days=7)
    services_with_data_retention = [x.service_id for x in flexible_data_retention]
    query = db.session.query(Notification).filter(func.date(Notification.created_at) < seven_days_ago,
                                                  Notification.notification_type == notification_type,
                                                  Notification.service_id.notin_(
                                                      services_with_data_retention))
    if notification_type == LETTER_TYPE:
        _delete_letters_from_s3(query=query)
    deleted += query.delete(synchronize_session='fetch')
    return deleted


def _delete_letters_from_s3(query):
    letters_to_delete_from_s3 = query.all()
    for letter in letters_to_delete_from_s3:
        bucket_name = current_app.config['LETTERS_PDF_BUCKET_NAME']
        # If the letter has not been sent there isn't a letter to delete from S3
        if letter.sent_at:
            sent_at = str(letter.sent_at.date())
            prefix = LETTERS_PDF_FILE_LOCATION_STRUCTURE.format(
                folder=sent_at,
                reference=letter.reference,
                duplex="D",
                letter_class="2",
                colour="C",
                crown="C" if letter.service.crown else "N",
                date=''
            ).upper()[:-5]
            s3_objects = get_s3_object_by_prefix(bucket_name=bucket_name, prefix=prefix)
            for s3_object in s3_objects:
                s3_object.delete()


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
    notifications = Notification.query.filter(
        Notification.created_at < timeout_start,
        Notification.status.in_(current_statuses),
        Notification.notification_type != LETTER_TYPE
    ).all()
    for table in [NotificationHistory, Notification]:
        q = table.query.filter(
            table.created_at < timeout_start,
            table.status.in_(current_statuses),
            table.notification_type != LETTER_TYPE
        )
        q.update(
            {'status': new_status, 'updated_at': updated_at},
            synchronize_session=False
        )
    # return a list of q = notification_ids in Notification table for sending delivery receipts
    return notifications


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
    technical_failure_notifications = timeout([NOTIFICATION_CREATED], NOTIFICATION_TECHNICAL_FAILURE)

    # Notifications still in sending or pending status are marked with a temporary-failure:
    temporary_failure_notifications = timeout([NOTIFICATION_SENDING, NOTIFICATION_PENDING],
                                              NOTIFICATION_TEMPORARY_FAILURE)

    db.session.commit()

    return technical_failure_notifications, temporary_failure_notifications


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
def dao_get_notifications_by_to_field(service_id, search_term, notification_type=None, statuses=None):
    if notification_type is None:
        notification_type = guess_notification_type(search_term)

    if notification_type == SMS_TYPE:
        normalised = try_validate_and_format_phone_number(search_term)

        for character in {'(', ')', ' ', '-'}:
            normalised = normalised.replace(character, '')

        normalised = normalised.lstrip('+0')

    elif notification_type == EMAIL_TYPE:
        try:
            normalised = validate_and_format_email_address(search_term)
        except InvalidEmailError:
            normalised = search_term.lower()

    else:
        raise InvalidRequest("Only email and SMS can use search by recipient", 400)

    normalised = escape_special_characters(normalised)

    filters = [
        Notification.service_id == service_id,
        Notification.normalised_to.like("%{}%".format(normalised)),
        Notification.key_type != KEY_TYPE_TEST,
    ]

    if statuses:
        filters.append(Notification.status.in_(statuses))
    if notification_type:
        filters.append(Notification.notification_type == notification_type)

    results = db.session.query(Notification).filter(*filters).order_by(desc(Notification.created_at)).all()
    return results


@statsd(namespace="dao")
def dao_get_notification_by_reference(reference):
    return Notification.query.filter(
        Notification.reference == reference
    ).one()


@statsd(namespace="dao")
def dao_get_notification_history_by_reference(reference):
    return NotificationHistory.query.filter(
        NotificationHistory.reference == reference
    ).one()


@statsd(namespace="dao")
def dao_get_notifications_by_references(references):
    return Notification.query.filter(
        Notification.reference.in_(references)
    ).all()


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


@statsd(namespace="dao")
def dao_get_last_notification_added_for_job_id(job_id):
    last_notification_added = Notification.query.filter(
        Notification.job_id == job_id
    ).order_by(
        Notification.job_row_number.desc()
    ).first()

    return last_notification_added


def dao_get_count_of_letters_to_process_for_date(date_to_process=None):
    """
    Returns a count of letter notifications to be processed today if no
    argument passed in otherwise will return the count for the date passed in.
    Records processed today = yesterday 17:30 to today 17:29:59

    Note - services in research mode are ignored
    """
    if date_to_process is None:
        date_to_process = date.today()

    day_before = date_to_process - timedelta(days=1)
    letter_deadline_time = current_app.config.get('LETTER_PROCESSING_DEADLINE')

    start_datetime = datetime.combine(day_before, letter_deadline_time)
    end_datetime = start_datetime + timedelta(days=1)

    count_of_letters_to_process_for_date = Notification.query.join(
        Service
    ).filter(
        Notification.created_at >= start_datetime,
        Notification.created_at < end_datetime,
        Notification.notification_type == LETTER_TYPE,
        Notification.status == NOTIFICATION_CREATED,
        Notification.key_type != KEY_TYPE_TEST,
        Service.research_mode.is_(False)
    ).count()

    return count_of_letters_to_process_for_date


def notifications_not_yet_sent(should_be_sending_after_seconds, notification_type):
    older_than_date = datetime.utcnow() - timedelta(seconds=should_be_sending_after_seconds)

    notifications = Notification.query.filter(
        Notification.created_at <= older_than_date,
        Notification.notification_type == notification_type,
        Notification.status == NOTIFICATION_CREATED
    ).all()
    return notifications


def guess_notification_type(search_term):
    if set(search_term) & set(string.ascii_letters + '@'):
        return EMAIL_TYPE
    else:
        return SMS_TYPE


@statsd(namespace='dao')
def fetch_aggregate_stats_by_date_range_for_all_services(start_date, end_date):
    start_date = get_london_midnight_in_utc(start_date)
    end_date = get_london_midnight_in_utc(end_date + timedelta(days=1))
    table = NotificationHistory

    if start_date >= datetime.utcnow() - timedelta(days=7):
        table = Notification

    query = db.session.query(
        table.notification_type,
        table.status,
        table.key_type,
        func.count(table.id).label('count')
    ).filter(
        table.created_at >= start_date,
        table.created_at < end_date
    ).group_by(
        table.notification_type,
        table.key_type,
        table.status
    ).order_by(
        table.notification_type,
    )

    return query.all()
