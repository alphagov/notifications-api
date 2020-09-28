import functools
from itertools import groupby
from operator import attrgetter
from datetime import (
    datetime,
    timedelta,
)

from botocore.exceptions import ClientError
from flask import current_app
from notifications_utils.international_billing_rates import INTERNATIONAL_BILLING_RATES
from notifications_utils.recipients import (
    validate_and_format_email_address,
    InvalidEmailError,
    try_validate_and_format_phone_number
)
from notifications_utils.timezones import convert_bst_to_utc, convert_utc_to_bst
from sqlalchemy import (desc, func, asc, and_, or_)
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.sql import functions
from sqlalchemy.sql.expression import case
from werkzeug.datastructures import MultiDict

from app import db, create_uuid
from app.aws.s3 import remove_s3_object, get_s3_bucket_objects
from app.dao.dao_utils import transactional
from app.letters.utils import get_letter_pdf_filename
from app.models import (
    FactNotificationStatus,
    Notification,
    NotificationHistory,
    ProviderDetails,
    KEY_TYPE_NORMAL,
    KEY_TYPE_TEST,
    LETTER_TYPE,
    NOTIFICATION_CREATED,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_SENDING,
    NOTIFICATION_PENDING,
    NOTIFICATION_PENDING_VIRUS_CHECK,
    NOTIFICATION_TECHNICAL_FAILURE,
    NOTIFICATION_TEMPORARY_FAILURE,
    NOTIFICATION_PERMANENT_FAILURE,
    NOTIFICATION_SENT,
    SMS_TYPE,
    EMAIL_TYPE,
    ServiceDataRetention,
    Service,
)
from app.utils import get_london_midnight_in_utc
from app.utils import midnight_n_days_ago, escape_special_characters
from app.clients.sms.firetext import get_message_status_and_reason_from_firetext_code


def dao_get_last_date_template_was_used(template_id, service_id):
    last_date_from_notifications = db.session.query(
        functions.max(Notification.created_at)
    ).filter(
        Notification.service_id == service_id,
        Notification.template_id == template_id,
        Notification.key_type != KEY_TYPE_TEST
    ).scalar()

    if last_date_from_notifications:
        return last_date_from_notifications

    last_date = db.session.query(
        functions.max(FactNotificationStatus.bst_date)
    ).filter(
        FactNotificationStatus.template_id == template_id,
        FactNotificationStatus.key_type != KEY_TYPE_TEST
    ).scalar()

    return last_date


@transactional
def dao_create_notification(notification):
    if not notification.id:
        # need to populate defaulted fields before we create the notification history object
        notification.id = create_uuid()
    if not notification.status:
        notification.status = NOTIFICATION_CREATED

    db.session.add(notification)


def _decide_permanent_temporary_failure(status, notification, detailed_status_code=None):
    # If we get failure status from Firetext, we want to know if this is temporary or permanent failure.
    # So we check the failure code to learn that.
    # If there is no failure code, or we do not recognise the failure code, we do the following:
    # if notifitcation goes form status pending to status failure, we mark it as temporary failure;
    # if notification goes straight to status failure, we mark it as permanent failure.
    if status == NOTIFICATION_PERMANENT_FAILURE and detailed_status_code not in [None, '000']:
        try:
            status, reason = get_message_status_and_reason_from_firetext_code(detailed_status_code)
            current_app.logger.info(f'Updating notification id {notification.id} to status {status}, reason: {reason}')
            return status
        except KeyError:
            current_app.logger.warning(f'Failure code {detailed_status_code} from Firetext not recognised')
    # fallback option:
    if notification.status == NOTIFICATION_PENDING and status == NOTIFICATION_PERMANENT_FAILURE:
        status = NOTIFICATION_TEMPORARY_FAILURE
    return status


def country_records_delivery(phone_prefix):
    dlr = INTERNATIONAL_BILLING_RATES[phone_prefix]['attributes']['dlr']
    return dlr and dlr.lower() == 'yes'


def _update_notification_status(notification, status, detailed_status_code=None):
    status = _decide_permanent_temporary_failure(
        status=status, notification=notification, detailed_status_code=detailed_status_code
    )
    notification.status = status
    dao_update_notification(notification)
    return notification


@transactional
def update_notification_status_by_id(notification_id, status, sent_by=None, detailed_status_code=None):
    notification = Notification.query.with_for_update().filter(Notification.id == notification_id).first()

    if not notification:
        current_app.logger.info('notification not found for id {} (update to status {})'.format(
            notification_id,
            status
        ))
        return None

    if notification.status not in {
        NOTIFICATION_CREATED,
        NOTIFICATION_SENDING,
        NOTIFICATION_PENDING,
        NOTIFICATION_SENT,
        NOTIFICATION_PENDING_VIRUS_CHECK
    }:
        _duplicate_update_warning(notification, status)
        return None

    if (
        notification.notification_type == SMS_TYPE
        and notification.international
        and not country_records_delivery(notification.phone_prefix)
    ):
        return None
    if not notification.sent_by and sent_by:
        notification.sent_by = sent_by
    return _update_notification_status(
        notification=notification,
        status=status,
        detailed_status_code=detailed_status_code
    )


@transactional
def update_notification_status_by_reference(reference, status):
    # this is used to update letters and emails
    notification = Notification.query.filter(Notification.reference == reference).first()

    if not notification:
        current_app.logger.error('notification not found for reference {} (update to {})'.format(reference, status))
        return None

    if notification.status not in {
        NOTIFICATION_SENDING,
        NOTIFICATION_PENDING
    }:
        _duplicate_update_warning(notification, status)
        return None

    return _update_notification_status(
        notification=notification,
        status=status
    )


@transactional
def dao_update_notification(notification):
    notification.updated_at = datetime.utcnow()
    db.session.add(notification)


def get_notification_for_job(service_id, job_id, notification_id):
    return Notification.query.filter_by(service_id=service_id, job_id=job_id, id=notification_id).one()


def get_notifications_for_job(service_id, job_id, filter_dict=None, page=1, page_size=None):
    if page_size is None:
        page_size = current_app.config['PAGE_SIZE']
    query = Notification.query.filter_by(service_id=service_id, job_id=job_id)
    query = _filter_query(query, filter_dict)
    return query.order_by(asc(Notification.job_row_number)).paginate(
        page=page,
        per_page=page_size
    )


def dao_get_notification_count_for_job_id(*, job_id):
    return Notification.query.filter_by(job_id=job_id).count()


def get_notification_with_personalisation(service_id, notification_id, key_type):
    filter_dict = {'service_id': service_id, 'id': notification_id}
    if key_type:
        filter_dict['key_type'] = key_type

    return Notification.query.filter_by(**filter_dict).options(joinedload('template')).one()


def get_notification_by_id(notification_id, service_id=None, _raise=False):
    filters = [Notification.id == notification_id]

    if service_id:
        filters.append(Notification.service_id == service_id)

    query = Notification.query.filter(*filters)

    return query.one() if _raise else query.first()


def get_notifications(filter_dict=None):
    return _filter_query(Notification.query, filter_dict=filter_dict)


def get_notifications_for_service(
        service_id,
        filter_dict=None,
        page=1,
        page_size=None,
        count_pages=True,
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
        per_page=page_size,
        count=count_pages
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
        query = query.filter(Notification.notification_type.in_(template_types))

    return query


def delete_notifications_older_than_retention_by_type(notification_type, qry_limit=50000):
    current_app.logger.info(
        'Deleting {} notifications for services with flexible data retention'.format(notification_type))

    flexible_data_retention = ServiceDataRetention.query.filter(
        ServiceDataRetention.notification_type == notification_type
    ).all()
    deleted = 0
    for f in flexible_data_retention:
        current_app.logger.info(
            "Deleting {} notifications for service id: {}".format(notification_type, f.service_id))

        day_to_delete_backwards_from = get_london_midnight_in_utc(
            convert_utc_to_bst(datetime.utcnow()).date()) - timedelta(days=f.days_of_retention)

        deleted += _move_notifications_to_notification_history(
            notification_type, f.service_id, day_to_delete_backwards_from, qry_limit)

    current_app.logger.info(
        'Deleting {} notifications for services without flexible data retention'.format(notification_type))

    seven_days_ago = get_london_midnight_in_utc(convert_utc_to_bst(datetime.utcnow()).date()) - timedelta(days=7)
    services_with_data_retention = [x.service_id for x in flexible_data_retention]
    service_ids_to_purge = db.session.query(Service.id).filter(Service.id.notin_(services_with_data_retention)).all()

    for service_id in service_ids_to_purge:
        deleted += _move_notifications_to_notification_history(
            notification_type, service_id, seven_days_ago, qry_limit)

    current_app.logger.info('Finished deleting {} notifications'.format(notification_type))

    return deleted


@transactional
def insert_notification_history_delete_notifications(
    notification_type, service_id, timestamp_to_delete_backwards_from, qry_limit=50000
):
    # Setting default query limit to 50,000 which take about 48 seconds on current table size
    # 10, 000 took 11s and 100,000 took 1 min 30 seconds.
    drop_table_if_exists = """
        DROP TABLE if exists NOTIFICATION_ARCHIVE
        """
    select_into_temp_table = """
         CREATE TEMP TABLE NOTIFICATION_ARCHIVE AS
         SELECT id, job_id, job_row_number, service_id, template_id, template_version, api_key_id,
             key_type, notification_type, created_at, sent_at, sent_by, updated_at, reference, billable_units,
             client_reference, international, phone_prefix, rate_multiplier, notification_status,
              created_by_id, postage, document_download_count
          FROM notifications
        WHERE service_id = :service_id
          AND notification_type = :notification_type
          AND created_at < :timestamp_to_delete_backwards_from
          AND key_type in ('normal', 'team')
        limit :qry_limit
        """
    # Insert into NotificationHistory if the row already exists do nothing.
    insert_query = """
        insert into notification_history
         SELECT * from NOTIFICATION_ARCHIVE
          ON CONFLICT ON CONSTRAINT notification_history_pkey
          DO NOTHING
    """
    delete_query = """
        DELETE FROM notifications
        where id in (select id from NOTIFICATION_ARCHIVE)
    """
    input_params = {
        "service_id": service_id,
        "notification_type": notification_type,
        "timestamp_to_delete_backwards_from": timestamp_to_delete_backwards_from,
        "qry_limit": qry_limit
    }

    db.session.execute(drop_table_if_exists)
    db.session.execute(select_into_temp_table, input_params)

    result = db.session.execute("select * from NOTIFICATION_ARCHIVE")

    db.session.execute(insert_query)

    db.session.execute(delete_query)

    db.session.execute("DROP TABLE NOTIFICATION_ARCHIVE")
    return result.rowcount


def _move_notifications_to_notification_history(notification_type, service_id, day_to_delete_backwards_from, qry_limit):
    deleted = 0
    if notification_type == LETTER_TYPE:
        _delete_letters_from_s3(
            notification_type, service_id, day_to_delete_backwards_from, qry_limit
        )
    delete_count_per_call = 1
    while delete_count_per_call > 0:
        delete_count_per_call = insert_notification_history_delete_notifications(
            notification_type=notification_type,
            service_id=service_id,
            timestamp_to_delete_backwards_from=day_to_delete_backwards_from,
            qry_limit=qry_limit
        )
        deleted += delete_count_per_call

    # Deleting test Notifications, test notifications are not persisted to NotificationHistory
    Notification.query.filter(
        Notification.notification_type == notification_type,
        Notification.service_id == service_id,
        Notification.created_at < day_to_delete_backwards_from,
        Notification.key_type == KEY_TYPE_TEST
    ).delete(synchronize_session=False)
    db.session.commit()

    return deleted


def _delete_letters_from_s3(
        notification_type, service_id, date_to_delete_from, query_limit
):
    letters_to_delete_from_s3 = db.session.query(
        Notification
    ).filter(
        Notification.notification_type == notification_type,
        Notification.created_at < date_to_delete_from,
        Notification.service_id == service_id
    ).limit(query_limit).all()
    for letter in letters_to_delete_from_s3:
        bucket_name = current_app.config['LETTERS_PDF_BUCKET_NAME']
        # I don't think we need this anymore, we should update the query to get letters sent 7 days ago
        if letter.sent_at:
            prefix = get_letter_pdf_filename(reference=letter.reference,
                                             crown=letter.service.crown,
                                             created_at=letter.created_at,
                                             ignore_folder=letter.key_type == KEY_TYPE_TEST,
                                             postage=letter.postage)
            s3_objects = get_s3_bucket_objects(bucket_name=bucket_name, subfolder=prefix)
            for s3_object in s3_objects:
                try:
                    remove_s3_object(bucket_name, s3_object['Key'])
                except ClientError:
                    current_app.logger.exception(
                        "Could not delete S3 object with filename: {}".format(s3_object['Key']))


@transactional
def dao_delete_notifications_by_id(notification_id):
    db.session.query(Notification).filter(
        Notification.id == notification_id
    ).delete(synchronize_session='fetch')


def _timeout_notifications(current_statuses, new_status, timeout_start, updated_at):
    notifications = Notification.query.filter(
        Notification.created_at < timeout_start,
        Notification.status.in_(current_statuses),
        Notification.notification_type != LETTER_TYPE
    ).all()
    Notification.query.filter(
        Notification.created_at < timeout_start,
        Notification.status.in_(current_statuses),
        Notification.notification_type != LETTER_TYPE
    ).update(
        {'status': new_status, 'updated_at': updated_at},
        synchronize_session=False
    )
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


def is_delivery_slow_for_providers(
        created_at,
        threshold,
        delivery_time,
):
    """
    Returns a dict of providers and whether they are currently slow or not. eg:
    {
        'mmg': True,
        'firetext': False
    }
    """
    slow_notification_counts = db.session.query(
        ProviderDetails.identifier,
        case(
            [(
                Notification.status == NOTIFICATION_DELIVERED,
                (Notification.updated_at - Notification.sent_at) >= delivery_time
            )],
            else_=(datetime.utcnow() - Notification.sent_at) >= delivery_time
        ).label("slow"),
        func.count().label('count')
    ).select_from(
        ProviderDetails
    ).outerjoin(
        Notification, and_(
            Notification.sent_by == ProviderDetails.identifier,
            Notification.created_at >= created_at,
            Notification.sent_at.isnot(None),
            Notification.status.in_([NOTIFICATION_DELIVERED, NOTIFICATION_PENDING, NOTIFICATION_SENDING]),
            Notification.key_type != KEY_TYPE_TEST
        )
    ).filter(
        ProviderDetails.notification_type == 'sms',
        ProviderDetails.active
    ).order_by(
        ProviderDetails.identifier
    ).group_by(
        ProviderDetails.identifier,
        "slow"
    )

    slow_providers = {}
    for provider, rows in groupby(slow_notification_counts, key=attrgetter('identifier')):
        rows = list(rows)
        total_notifications = sum(row.count for row in rows)
        slow_notifications = sum(row.count for row in rows if row.slow)

        slow_providers[provider] = (slow_notifications / total_notifications >= threshold)

        current_app.logger.info("Slow delivery notifications count for provider {}: {} out of {}. Ratio {}".format(
            provider, slow_notifications, total_notifications, slow_notifications / total_notifications
        ))

    return slow_providers


@transactional
def dao_update_notifications_by_reference(references, update_dict):
    updated_count = Notification.query.filter(
        Notification.reference.in_(references)
    ).update(
        update_dict,
        synchronize_session=False
    )

    updated_history_count = 0
    if updated_count != len(references):
        updated_history_count = NotificationHistory.query.filter(
            NotificationHistory.reference.in_(references)
        ).update(
            update_dict,
            synchronize_session=False
        )

    return updated_count, updated_history_count


def dao_get_notifications_by_recipient_or_reference(
    service_id,
    search_term,
    notification_type=None,
    statuses=None,
    page=1,
    page_size=None,
):

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

    elif notification_type in {LETTER_TYPE, None}:
        # For letters, we store the address without spaces, so we need
        # to removes spaces from the search term to match. We also do
        # this when a notification type isn’t provided (this will
        # happen if a user doesn’t have permission to see the dashboard)
        # because email addresses and phone numbers will never be stored
        # with spaces either.
        normalised = ''.join(search_term.split()).lower()

    else:
        raise TypeError(
            f'Notification type must be {EMAIL_TYPE}, {SMS_TYPE}, {LETTER_TYPE} or None'
        )

    normalised = escape_special_characters(normalised)
    search_term = escape_special_characters(search_term)

    filters = [
        Notification.service_id == service_id,
        or_(
            Notification.normalised_to.like("%{}%".format(normalised)),
            Notification.client_reference.ilike("%{}%".format(search_term)),
        ),
        Notification.key_type != KEY_TYPE_TEST,
    ]

    if statuses:
        filters.append(Notification.status.in_(statuses))
    if notification_type:
        filters.append(Notification.notification_type == notification_type)

    results = db.session.query(Notification)\
        .filter(*filters)\
        .order_by(desc(Notification.created_at))\
        .paginate(page=page, per_page=page_size)
    return results


def dao_get_notification_by_reference(reference):
    return Notification.query.filter(
        Notification.reference == reference
    ).one()


def dao_get_notification_or_history_by_reference(reference):
    try:
        # This try except is necessary because in test keys and research mode does not create notification history.
        # Otherwise we could just search for the NotificationHistory object
        return Notification.query.filter(
            Notification.reference == reference
        ).one()
    except NoResultFound:
        return NotificationHistory.query.filter(
            NotificationHistory.reference == reference
        ).one()


def dao_get_notifications_by_references(references):
    return Notification.query.filter(
        Notification.reference.in_(references)
    ).all()


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
    under_10_secs = Notification.sent_at - Notification.created_at <= timedelta(seconds=10)
    sum_column = functions.coalesce(functions.sum(
        case(
            [
                (under_10_secs, 1)
            ],
            else_=0
        )
    ), 0)

    return db.session.query(
        func.count(Notification.id).label('messages_total'),
        sum_column.label('messages_within_10_secs')
    ).filter(
        Notification.created_at >= start_date,
        Notification.created_at < end_date,
        Notification.api_key_id.isnot(None),
        Notification.key_type != KEY_TYPE_TEST,
        Notification.notification_type != LETTER_TYPE
    ).one()


def dao_get_last_notification_added_for_job_id(job_id):
    last_notification_added = Notification.query.filter(
        Notification.job_id == job_id
    ).order_by(
        Notification.job_row_number.desc()
    ).first()

    return last_notification_added


def notifications_not_yet_sent(should_be_sending_after_seconds, notification_type):
    older_than_date = datetime.utcnow() - timedelta(seconds=should_be_sending_after_seconds)

    notifications = Notification.query.filter(
        Notification.created_at <= older_than_date,
        Notification.notification_type == notification_type,
        Notification.status == NOTIFICATION_CREATED
    ).all()
    return notifications


def dao_get_letters_to_be_printed(print_run_deadline, postage):
    """
    Return all letters created before the print run deadline that have not yet been sent
    """
    notifications = Notification.query.filter(
        Notification.created_at < convert_bst_to_utc(print_run_deadline),
        Notification.notification_type == LETTER_TYPE,
        Notification.status == NOTIFICATION_CREATED,
        Notification.key_type == KEY_TYPE_NORMAL,
        Notification.postage == postage,
    ).order_by(
        Notification.created_at
    ).all()
    return notifications


def dao_old_letters_with_created_status():
    yesterday_bst = convert_utc_to_bst(datetime.utcnow()) - timedelta(days=1)
    last_processing_deadline = yesterday_bst.replace(hour=17, minute=30, second=0, microsecond=0)

    notifications = Notification.query.filter(
        Notification.created_at < convert_bst_to_utc(last_processing_deadline),
        Notification.notification_type == LETTER_TYPE,
        Notification.status == NOTIFICATION_CREATED
    ).order_by(
        Notification.created_at
    ).all()
    return notifications


def letters_missing_from_sending_bucket(seconds_to_subtract):
    older_than_date = datetime.utcnow() - timedelta(seconds=seconds_to_subtract)
    # We expect letters to have a `created` status, updated_at timestamp and billable units greater than zero.
    notifications = Notification.query.filter(
        Notification.billable_units == 0,
        Notification.updated_at == None,  # noqa
        Notification.status == NOTIFICATION_CREATED,
        Notification.created_at <= older_than_date,
        Notification.notification_type == LETTER_TYPE,
        Notification.key_type == KEY_TYPE_NORMAL
    ).order_by(
        Notification.created_at
    ).all()

    return notifications


def dao_precompiled_letters_still_pending_virus_check():
    ninety_minutes_ago = datetime.utcnow() - timedelta(seconds=5400)

    notifications = Notification.query.filter(
        Notification.created_at < ninety_minutes_ago,
        Notification.status == NOTIFICATION_PENDING_VIRUS_CHECK
    ).order_by(
        Notification.created_at
    ).all()
    return notifications


def _duplicate_update_warning(notification, status):
    current_app.logger.info(
        (
            'Duplicate callback received. Notification id {id} received a status update to {new_status}'
            '{time_diff} after being set to {old_status}. {type} sent by {sent_by}'
        ).format(
            id=notification.id,
            old_status=notification.status,
            new_status=status,
            time_diff=datetime.utcnow() - (notification.updated_at or notification.created_at),
            type=notification.notification_type,
            sent_by=notification.sent_by
        )
    )
