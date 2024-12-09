import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import groupby
from operator import attrgetter

from botocore.exceptions import ClientError
from dateutil.relativedelta import relativedelta
from flask import current_app
from notifications_utils.international_billing_rates import (
    INTERNATIONAL_BILLING_RATES,
)
from notifications_utils.recipient_validation.email_address import validate_and_format_email_address
from notifications_utils.recipient_validation.errors import InvalidEmailError
from notifications_utils.recipient_validation.phone_number import try_validate_and_format_phone_number
from notifications_utils.timezones import convert_bst_to_utc, convert_utc_to_bst
from sqlalchemy import and_, asc, desc, func, literal, or_, union
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import defer, joinedload, undefer
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.sql import functions
from sqlalchemy.sql.expression import case
from werkzeug.datastructures import MultiDict

from app import create_uuid, db
from app.clients.sms.firetext import (
    get_message_status_and_reason_from_firetext_code,
)
from app.constants import (
    EMAIL_TYPE,
    KEY_TYPE_NORMAL,
    KEY_TYPE_TEST,
    LETTER_TYPE,
    NOTIFICATION_CREATED,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_PENDING,
    NOTIFICATION_PENDING_VIRUS_CHECK,
    NOTIFICATION_PERMANENT_FAILURE,
    NOTIFICATION_SENDING,
    NOTIFICATION_SENT,
    NOTIFICATION_STATUS_TYPES,
    NOTIFICATION_STATUS_TYPES_COMPLETED,
    NOTIFICATION_STATUS_TYPES_DEPRECATED,
    NOTIFICATION_TEMPORARY_FAILURE,
    SMS_TYPE,
)
from app.dao.dao_utils import autocommit
from app.letters.utils import LetterPDFNotFound, find_letter_pdf_in_s3
from app.models import (
    FactNotificationStatus,
    LetterCostThreshold,
    Notification,
    NotificationAllTimeView,
    NotificationHistory,
    NotificationLetterDespatch,
    ProviderDetails,
)
from app.utils import (
    escape_special_characters,
    get_london_midnight_in_utc,
    midnight_n_days_ago,
)

FIELDS_TO_TRANSFER_TO_NOTIFICATION_HISTORY = [
    "id",
    "job_id",
    "job_row_number",
    "service_id",
    "template_id",
    "template_version",
    "api_key_id",
    "key_type",
    "notification_type",
    "created_at",
    "sent_at",
    "sent_by",
    "updated_at",
    "reference",
    "billable_units",
    "client_reference",
    "international",
    "phone_prefix",
    "rate_multiplier",
    "notification_status",
    "created_by_id",
    "postage",
    "document_download_count",
]


def dao_get_last_date_template_was_used(template_id, service_id):
    # first, just check if there are any rows present for this template in the notification table.
    # we can use the ix_notifications_template_id. If there are rows, then lets check to find out exactly
    # when the most recent created date was (also checking key type test too)
    if db.session.query(Notification.query.filter(Notification.template_id == template_id).exists()).scalar():
        last_date_from_notifications = (
            db.session.query(functions.max(Notification.created_at))
            .filter(
                Notification.service_id == service_id,
                Notification.template_id == template_id,
                Notification.key_type != KEY_TYPE_TEST,
            )
            .scalar()
        )

        if last_date_from_notifications:
            return last_date_from_notifications

    if db.session.query(
        FactNotificationStatus.query.filter(FactNotificationStatus.template_id == template_id).exists()
    ).scalar():
        last_date = (
            db.session.query(functions.max(FactNotificationStatus.bst_date))
            .filter(
                FactNotificationStatus.template_id == template_id,
                FactNotificationStatus.key_type != KEY_TYPE_TEST,
                FactNotificationStatus.bst_date > datetime.now() - relativedelta(years=1),
            )
            .scalar()
        )

        return last_date

    return None


@autocommit
def dao_create_notification(notification):
    if not notification.id:
        # need to populate defaulted fields before we create the notification history object
        notification.id = create_uuid()
    if not notification.status:
        notification.status = NOTIFICATION_CREATED

    db.session.add(notification)


def _decide_permanent_temporary_failure(status, notification, detailed_status_code=None):
    # Firetext will send us a pending status, followed by a success or failure status.
    # When we get a failure status we need to look at the detailed_status_code to determine if the failure type
    # is a permanent-failure or temporary-failure.
    if notification.sent_by == "firetext":
        if status == NOTIFICATION_PERMANENT_FAILURE and detailed_status_code:
            try:
                status, reason = get_message_status_and_reason_from_firetext_code(detailed_status_code)
                current_app.logger.info(
                    "Updating notification id %s to status %s, reason: %s", notification.id, status, reason
                )
                return status
            except KeyError:
                current_app.logger.warning("Failure code %s from Firetext not recognised", detailed_status_code)
        # fallback option:
        if status == NOTIFICATION_PERMANENT_FAILURE and notification.status == NOTIFICATION_PENDING:
            status = NOTIFICATION_TEMPORARY_FAILURE
    return status


def country_records_delivery(phone_prefix):
    dlr = INTERNATIONAL_BILLING_RATES[phone_prefix]["attributes"]["dlr"]
    return dlr and dlr.lower() == "yes"


def _update_notification_status(notification, status, detailed_status_code=None):
    status = _decide_permanent_temporary_failure(
        status=status, notification=notification, detailed_status_code=detailed_status_code
    )
    notification.status = status
    dao_update_notification(notification)
    return notification


@autocommit
def update_notification_status_by_id(notification_id, status, sent_by=None, detailed_status_code=None):
    notification = Notification.query.with_for_update().filter(Notification.id == notification_id).first()

    if not notification:
        current_app.logger.info("notification not found for id %s (update to status %s)", notification_id, status)
        return None

    if notification.status not in {
        NOTIFICATION_CREATED,
        NOTIFICATION_SENDING,
        NOTIFICATION_PENDING,
        NOTIFICATION_SENT,
        NOTIFICATION_PENDING_VIRUS_CHECK,
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
        notification=notification, status=status, detailed_status_code=detailed_status_code
    )


@autocommit
def dao_update_notification(notification):
    notification.updated_at = datetime.utcnow()
    db.session.add(notification)


def get_notifications_for_job(service_id, job_id, filter_dict=None, page=1, page_size=None):
    if page_size is None:
        page_size = current_app.config["PAGE_SIZE"]
    query = Notification.query.filter_by(service_id=service_id, job_id=job_id)
    query = _filter_query(query, filter_dict)
    return query.order_by(asc(Notification.job_row_number)).paginate(page=page, per_page=page_size)


def dao_get_notification_count_for_job_id(*, job_id):
    return Notification.query.filter_by(job_id=job_id).count()


def get_notification_with_personalisation(service_id, notification_id, key_type):
    filter_dict = {"service_id": service_id, "id": notification_id}
    if key_type:
        filter_dict["key_type"] = key_type

    return Notification.query.filter_by(**filter_dict).options(joinedload("template")).one()


def get_notification_by_id(notification_id, service_id=None, _raise=False):
    filters = [Notification.id == notification_id]

    if service_id:
        filters.append(Notification.service_id == service_id)

    query = Notification.query.filter(*filters)

    return query.one() if _raise else query.first()


def dao_get_notification_or_history_by_id(notification_id):
    if notification := Notification.query.get(notification_id):
        return notification
    else:
        return NotificationHistory.query.get(notification_id)


def get_notifications_for_service(  # noqa: C901
    service_id,
    filter_dict=None,
    page=1,
    page_size=None,
    count_pages=True,
    limit_days=None,
    key_type=None,
    with_template=False,
    with_personalisation=True,
    include_jobs=False,
    include_from_test_key=False,
    older_than=None,
    client_reference=None,
    include_one_off=True,
    error_out=True,
):
    if page_size is None:
        page_size = current_app.config["PAGE_SIZE"]

    filters = [Notification.service_id == service_id]

    if limit_days is not None:
        filters.append(Notification.created_at >= midnight_n_days_ago(limit_days))

    if older_than is not None:
        # fetching this separately and including in query as literal makes it visible to
        # the planner
        older_than_created_at = (
            db.session.query(Notification.created_at)
            .filter(Notification.id == older_than, Notification.service_id == service_id)
            .scalar()
        )
        if older_than_created_at is None:
            # ensure we return no results
            filters.append(False)
        else:
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

    if with_template:
        query = query.options(joinedload("template"))

    query = query.options((undefer if with_personalisation else defer)("_personalisation"))

    query = query.options(joinedload("api_key"))

    return query.order_by(desc(Notification.created_at)).paginate(
        page=page,
        per_page=page_size,
        count=count_pages,
        error_out=error_out,
    )


def _filter_query(query, filter_dict=None):
    if filter_dict is None:
        return query

    multidict = MultiDict(filter_dict)

    # filter by status
    statuses = multidict.getlist("status")
    if statuses:
        statuses = Notification.substitute_status(statuses)
        if not set(statuses).issuperset(set(NOTIFICATION_STATUS_TYPES) - set(NOTIFICATION_STATUS_TYPES_DEPRECATED)):
            query = query.filter(Notification.status.in_(statuses))

    # filter by template
    template_types = multidict.getlist("template_type")
    if template_types:
        query = query.filter(Notification.notification_type.in_(template_types))

    return query


@autocommit
def insert_notification_history_delete_notifications(
    notification_type, service_id, timestamp_to_delete_backwards_from, qry_limit=50000
):
    """
    Delete up to 50,000 notifications that are past retention for a notification type and service.


    Steps are as follows:

    Create a temporary notifications table
    Populate that table with up to 50k notifications that are to be deleted. (Note: no specified order)
    Insert everything in the temp table into notification history
    Delete from notifications if notification id is in the temp table
    Drop the temp table (automatically when the transaction commits)

    Temporary tables are in a separate postgres schema, and only visible to the current session (db connection,
    in a celery task there's one connection per thread.)
    """
    # Setting default query limit to 50,000 which take about 48 seconds on current table size
    # 10, 000 took 11s and 100,000 took 1 min 30 seconds.
    fields_to_transfer_to_notification_history = ", ".join(FIELDS_TO_TRANSFER_TO_NOTIFICATION_HISTORY)

    select_into_temp_table = f"""
         CREATE TEMP TABLE NOTIFICATION_ARCHIVE ON COMMIT DROP AS
         SELECT {fields_to_transfer_to_notification_history}
          FROM notifications
        WHERE service_id = :service_id
          AND notification_type = :notification_type
          AND created_at < :timestamp_to_delete_backwards_from
          AND key_type in ('normal', 'team')
        ORDER BY created_at
        limit :qry_limit
        """
    select_into_temp_table_for_letters = f"""
         CREATE TEMP TABLE NOTIFICATION_ARCHIVE ON COMMIT DROP AS
         SELECT {fields_to_transfer_to_notification_history}
          FROM notifications
        WHERE service_id = :service_id
          AND notification_type = :notification_type
          AND created_at < :timestamp_to_delete_backwards_from
          AND notification_status NOT IN ('pending-virus-check', 'created', 'sending')
          AND key_type in ('normal', 'team')
        ORDER BY created_at
        limit :qry_limit
        """
    # Insert into NotificationHistory if the row already exists do nothing.
    insert_query = f"""
        insert into notification_history ({fields_to_transfer_to_notification_history})
         SELECT {fields_to_transfer_to_notification_history} from NOTIFICATION_ARCHIVE
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
        "qry_limit": qry_limit,
    }

    select_to_use = select_into_temp_table_for_letters if notification_type == "letter" else select_into_temp_table
    db.session.execute(select_to_use, input_params)

    result = db.session.execute("select count(*) from NOTIFICATION_ARCHIVE").fetchone()[0]

    db.session.execute(insert_query)

    db.session.execute(delete_query)

    return result


def move_notifications_to_notification_history(
    notification_type, service_id, timestamp_to_delete_backwards_from, qry_limit=50000
):
    if notification_type == LETTER_TYPE:
        # reduced query limit so we don't run into issues trying to loop through 50k letters in python deleting from s3
        # use `min` so we can reduce query limit artificially during unit tests
        qry_limit = min(qry_limit, 5_000)

        _delete_letters_from_s3(notification_type, service_id, timestamp_to_delete_backwards_from, qry_limit)

    return insert_notification_history_delete_notifications(
        notification_type=notification_type,
        service_id=service_id,
        timestamp_to_delete_backwards_from=timestamp_to_delete_backwards_from,
        qry_limit=qry_limit,
    )


def delete_test_notifications(notification_type, service_id, timestamp_to_delete_backwards_from):
    # Deleting test Notifications, test notifications are not persisted to NotificationHistory
    Notification.query.filter(
        Notification.notification_type == notification_type,
        Notification.service_id == service_id,
        Notification.created_at < timestamp_to_delete_backwards_from,
        Notification.key_type == KEY_TYPE_TEST,
    ).delete(synchronize_session=False)

    db.session.commit()


def _delete_letters_from_s3(notification_type, service_id, date_to_delete_from, query_limit):
    letters_to_delete_from_s3 = (
        db.session.query(Notification)
        .filter(
            Notification.notification_type == notification_type,
            Notification.created_at < date_to_delete_from,
            Notification.service_id == service_id,
            # although letters in non completed statuses do have PDFs in s3, they do not exist in the
            # production-letters-pdf bucket as they never made it that far so we do not try and delete
            # them from it
            Notification.status.in_(NOTIFICATION_STATUS_TYPES_COMPLETED),
        )
        .order_by(Notification.created_at)
        .limit(query_limit)
        .all()
    )
    for letter in letters_to_delete_from_s3:
        try:
            letter_pdf = find_letter_pdf_in_s3(letter)
            letter_pdf.delete()
        except ClientError:
            current_app.logger.exception("Error deleting S3 object for letter: %s", letter.id)
        except LetterPDFNotFound:
            current_app.logger.warning("No S3 object to delete for letter: %s", letter.id)


@autocommit
def dao_delete_notifications_by_id(notification_id):
    db.session.query(Notification).filter(Notification.id == notification_id).delete(synchronize_session="fetch")


def dao_timeout_notifications(cutoff_time, limit=100000):
    """
    Set email and SMS notifications (only) to "temporary-failure" status
    if they're still sending from before the specified cutoff_time.
    """
    updated_at = datetime.utcnow()
    current_statuses = [NOTIFICATION_SENDING, NOTIFICATION_PENDING]
    new_status = NOTIFICATION_TEMPORARY_FAILURE

    notifications = (
        Notification.query.filter(
            Notification.created_at < cutoff_time,
            Notification.status.in_(current_statuses),
            Notification.notification_type.in_([SMS_TYPE, EMAIL_TYPE]),
        )
        .limit(limit)
        .all()
    )

    Notification.query.filter(
        Notification.id.in_([n.id for n in notifications]),
    ).update({"status": new_status, "updated_at": updated_at}, synchronize_session=False)

    db.session.commit()
    return notifications


def is_delivery_slow_for_providers(
    created_within_minutes,
    delivered_within_minutes,
    threshold,
):
    """
    Returns a dict of providers and whether they are currently slow or not. eg:
    {
        'mmg': True,
        'firetext': False
    }

    A provider is considered slow if more than the `threshold` of their messages
    sent in the last `created_within_minutes` minutes took over
    `delivered_within_minutes` minutes to be delivered
    """
    providers_slow_delivery_reports = get_slow_text_message_delivery_reports_by_provider(
        created_within_minutes, delivered_within_minutes
    )

    slow_providers = {}
    for report in providers_slow_delivery_reports:
        slow_providers[report.provider] = report.slow_ratio >= threshold

    return slow_providers


@dataclass
class SlowProviderDeliveryReport:
    provider: str
    slow_ratio: float
    slow_notifications: int
    total_notifications: int


def get_slow_text_message_delivery_reports_by_provider(
    created_within_minutes, delivered_within_minutes
) -> list[SlowProviderDeliveryReport]:
    """
    Returns a dict of providers with the ratio of their messages sent in the
    last `created_within_minutes` minutes that took over
    `delivered_within_minutes` minutes to be delivered

    {
        'mmg': 0.4,
        'firetext': 0.12
    }
    """
    created_since = datetime.utcnow() - timedelta(minutes=created_within_minutes)
    delivery_time = timedelta(minutes=delivered_within_minutes)
    slow_notification_counts = (
        db.session.query(
            ProviderDetails.identifier,
            case(
                [
                    (
                        Notification.status == NOTIFICATION_DELIVERED,
                        (Notification.updated_at - Notification.sent_at) >= delivery_time,
                    )
                ],
                else_=(datetime.utcnow() - Notification.sent_at) >= delivery_time,
            ).label("slow"),
            func.count().label("count"),
        )
        .select_from(ProviderDetails)
        .outerjoin(
            Notification,
            and_(
                Notification.notification_type == SMS_TYPE,
                Notification.sent_by == ProviderDetails.identifier,
                Notification.created_at >= created_since,
                Notification.sent_at.isnot(None),
                Notification.status.in_([NOTIFICATION_DELIVERED, NOTIFICATION_PENDING, NOTIFICATION_SENDING]),
                Notification.key_type != KEY_TYPE_TEST,
            ),
        )
        .filter(ProviderDetails.notification_type == "sms", ProviderDetails.active)
        .order_by(ProviderDetails.identifier)
        .group_by(ProviderDetails.identifier, "slow")
    )

    providers_slow_delivery_reports = []
    for provider, rows in groupby(slow_notification_counts, key=attrgetter("identifier")):
        rows = list(rows)
        total_notifications = sum(row.count for row in rows)
        slow_notifications = sum(row.count for row in rows if row.slow)
        providers_slow_delivery_reports.append(
            SlowProviderDeliveryReport(
                provider=provider,
                slow_ratio=slow_notifications / total_notifications,
                slow_notifications=slow_notifications,
                total_notifications=total_notifications,
            )
        )

    return providers_slow_delivery_reports


@autocommit
def dao_update_notifications_by_reference(references, update_dict):
    updated_count = Notification.query.filter(Notification.reference.in_(references)).update(
        update_dict, synchronize_session=False
    )

    updated_history_count = 0
    if updated_count != len(references):
        updated_history_count = NotificationHistory.query.filter(NotificationHistory.reference.in_(references)).update(
            update_dict, synchronize_session=False
        )

    return updated_count, updated_history_count


def dao_get_notifications_by_recipient_or_reference(
    service_id,
    search_term,
    notification_type=None,
    statuses=None,
    page=1,
    page_size=None,
    error_out=True,
):
    if notification_type == SMS_TYPE:
        normalised = try_validate_and_format_phone_number(search_term)

        for character in {"(", ")", " ", "-"}:
            normalised = normalised.replace(character, "")

        normalised = normalised.lstrip("+0")

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
        normalised = "".join(search_term.split()).lower()

    else:
        raise TypeError(f"Notification type must be {EMAIL_TYPE}, {SMS_TYPE}, {LETTER_TYPE} or None")

    normalised = escape_special_characters(normalised)
    search_term = escape_special_characters(search_term)

    filters = [
        Notification.service_id == service_id,
        or_(
            Notification.normalised_to.like(f"%{normalised}%"),
            Notification.client_reference.ilike(f"%{search_term}%"),
        ),
        Notification.key_type != KEY_TYPE_TEST,
    ]

    if statuses:
        filters.append(Notification.status.in_(statuses))
    if notification_type:
        filters.append(Notification.notification_type == notification_type)

    results = (
        db.session.query(Notification)
        .filter(*filters)
        .order_by(desc(Notification.created_at))
        .paginate(page=page, per_page=page_size, count=False, error_out=error_out)
    )
    return results


def dao_get_notification_by_reference(reference):
    return Notification.query.filter(Notification.reference == reference).one()


def dao_get_notification_or_history_by_reference(reference):
    try:
        # This try except is necessary because test keys do not create notification history.
        # Otherwise we could just search for the NotificationHistory object
        return Notification.query.filter(Notification.reference == reference).one()
    except NoResultFound:
        return NotificationHistory.query.filter(NotificationHistory.reference == reference).one()


def dao_get_notifications_processing_time_stats(start_date, end_date):
    """
    For a given time range, returns the number of notifications sent and the number of
    those notifications that we processed within 10 seconds

    SELECT
    count(notifications),
    coalesce(sum(CASE WHEN sent_at - created_at <= interval '10 seconds' THEN 1 ELSE 0 END), 0)
    FROM notifications
    WHERE
    created_at > 'START DATE' AND
    created_at < 'END DATE' AND
    api_key_id IS NOT NULL AND
    key_type != 'test' AND
    notification_type != 'letter';
    """
    under_10_secs = Notification.sent_at - Notification.created_at <= timedelta(seconds=10)
    sum_column = functions.coalesce(functions.sum(case([(under_10_secs, 1)], else_=0)), 0)

    return (
        db.session.query(
            func.count(Notification.id).label("messages_total"), sum_column.label("messages_within_10_secs")
        )
        .filter(
            Notification.created_at >= start_date,
            Notification.created_at < end_date,
            Notification.api_key_id.isnot(None),
            Notification.key_type != KEY_TYPE_TEST,
            Notification.notification_type != LETTER_TYPE,
        )
        .one()
    )


def dao_get_last_notification_added_for_job_id(job_id):
    last_notification_added = (
        Notification.query.filter(Notification.job_id == job_id).order_by(Notification.job_row_number.desc()).first()
    )

    return last_notification_added


def notifications_not_yet_sent(should_be_sending_after_seconds, notification_type):
    older_than_date = datetime.utcnow() - timedelta(seconds=should_be_sending_after_seconds)

    notifications = Notification.query.filter(
        Notification.created_at <= older_than_date,
        Notification.notification_type == notification_type,
        Notification.status == NOTIFICATION_CREATED,
    ).all()
    return notifications


def dao_get_letters_to_be_printed(print_run_deadline_local, query_limit=10000):
    """
    Return all letters created before the print run deadline that have not yet been sent. This yields in batches of 10k
    to prevent the query taking too long and eating up too much memory. As each 10k batch is yielded, we'll start
    sending off to the DVLA via https

    CAUTION! Modify this query with caution. Modifying filters etc is fine, but if we join onto another table, then
    there may be undefined behaviour. Essentially we need each ORM object returned for each row to be unique,
    and we should avoid modifying state of returned objects.

    For more reading:
    https://docs.sqlalchemy.org/en/13/orm/query.html?highlight=yield_per#sqlalchemy.orm.query.Query.yield_per
    https://www.mail-archive.com/sqlalchemy@googlegroups.com/msg12443.html
    """
    notifications = (
        Notification.query.with_entities(Notification.id)
        .filter(
            Notification.created_at < convert_bst_to_utc(print_run_deadline_local),
            Notification.notification_type == LETTER_TYPE,
            Notification.status == NOTIFICATION_CREATED,
            Notification.key_type == KEY_TYPE_NORMAL,
            # we need billable_units as if a letter is stuck pre-validation, it'll be in state created but won't have a
            # generated (or sanitised if precompiled) pdf associated with it.
            Notification.billable_units > 0,
        )
        .yield_per(query_limit)
    )
    return notifications


def dao_get_letters_and_sheets_volume_by_postage(print_run_deadline_local):
    notifications = (
        db.session.query(
            func.count(Notification.id).label("letters_count"),
            func.sum(Notification.billable_units).label("sheets_count"),
            Notification.postage,
        )
        .filter(
            Notification.created_at < convert_bst_to_utc(print_run_deadline_local),
            Notification.notification_type == LETTER_TYPE,
            Notification.status == NOTIFICATION_CREATED,
            Notification.key_type == KEY_TYPE_NORMAL,
            Notification.billable_units > 0,
        )
        .group_by(Notification.postage)
        .order_by(Notification.postage)
        .all()
    )
    return notifications


def dao_old_letters_with_created_status():
    yesterday_bst = convert_utc_to_bst(datetime.utcnow()) - timedelta(days=1)
    last_processing_deadline = yesterday_bst.replace(hour=17, minute=30, second=0, microsecond=0)

    notifications = (
        Notification.query.filter(
            Notification.created_at < convert_bst_to_utc(last_processing_deadline),
            Notification.notification_type == LETTER_TYPE,
            Notification.status == NOTIFICATION_CREATED,
        )
        .order_by(Notification.created_at)
        .all()
    )
    return notifications


def letters_missing_from_sending_bucket(seconds_to_subtract):
    older_than_date = datetime.utcnow() - timedelta(seconds=seconds_to_subtract)
    # We expect letters to have a `created` status, updated_at timestamp and billable units greater than zero.
    notifications = (
        Notification.query.filter(
            Notification.billable_units == 0,
            Notification.updated_at == None,  # noqa
            Notification.status == NOTIFICATION_CREATED,
            Notification.created_at <= older_than_date,
            Notification.notification_type == LETTER_TYPE,
            Notification.key_type == KEY_TYPE_NORMAL,
        )
        .order_by(Notification.created_at)
        .all()
    )

    return notifications


def dao_precompiled_letters_still_pending_virus_check(max_minutes_ago_to_check):
    earliest_timestamp_to_check = datetime.utcnow() - timedelta(minutes=max_minutes_ago_to_check)
    ten_minutes_ago = datetime.utcnow() - timedelta(minutes=10)

    notifications = (
        Notification.query.filter(
            Notification.created_at > earliest_timestamp_to_check,
            Notification.created_at < ten_minutes_ago,
            Notification.status == NOTIFICATION_PENDING_VIRUS_CHECK,
            Notification.notification_type == LETTER_TYPE,
        )
        .order_by(Notification.created_at)
        .all()
    )
    return notifications


def _duplicate_update_warning(notification, status):
    time_diff = datetime.utcnow() - (notification.updated_at or notification.created_at)
    current_app.logger.info(
        "Duplicate callback received for service %(service_id)s. Notification ID %(notification_id)s with "
        "type %(type)s sent by %(sent_by)s. "
        "New status was %(new_status)s, current status is %(current_status)s. "
        "This happened %(time_diff)s after being first set.",
        {
            "service_id": notification.service_id,
            "notification_id": notification.id,
            "type": notification.notification_type,
            "sent_by": notification.sent_by,
            "new_status": status,
            "current_status": notification.status,
            "time_diff": time_diff,
        },
    )


def get_service_ids_with_notifications_before(notification_type, timestamp):
    return {
        row.service_id
        for row in db.session.query(Notification.service_id)
        .filter(Notification.notification_type == notification_type, Notification.created_at < timestamp)
        .distinct()
    }


def get_service_ids_with_notifications_on_date(notification_type, date):
    start_date = get_london_midnight_in_utc(date)
    end_date = get_london_midnight_in_utc(date + timedelta(days=1))

    notification_table_query = db.session.query(Notification.service_id.label("service_id")).filter(
        Notification.notification_type == notification_type,
        # using >= + < is much more efficient than date(created_at)
        Notification.created_at >= start_date,
        Notification.created_at < end_date,
    )

    # Looking at this table is more efficient for historical notifications,
    # provided the task to populate it has run before they were archived.
    ft_status_table_query = db.session.query(FactNotificationStatus.service_id.label("service_id")).filter(
        FactNotificationStatus.notification_type == notification_type,
        FactNotificationStatus.bst_date == date,
    )

    return {
        row.service_id
        for row in db.session.query(union(notification_table_query, ft_status_table_query).subquery()).distinct()
    }


@autocommit
def dao_record_letter_despatched_on(reference: str, despatched_on: datetime.date, cost_threshold: LetterCostThreshold):
    stmt = (
        insert(NotificationLetterDespatch)
        .from_select(
            ["notification_id", "despatched_on", "cost_threshold"],
            NotificationAllTimeView.query.with_entities(
                NotificationAllTimeView.id,
                literal(despatched_on),
                literal(cost_threshold.value),
            ).filter(NotificationAllTimeView.reference == reference),
        )
        .on_conflict_do_update(
            index_elements=["notification_id"],
            set_={"despatched_on": despatched_on, "cost_threshold": cost_threshold.value},
        )
    )

    db.session.execute(stmt)


@autocommit
def dao_record_letter_despatched_on_by_id(
    notification_id: uuid.UUID,
    despatched_on: datetime.date,
    cost_threshold: LetterCostThreshold,
):
    stmt = (
        insert(NotificationLetterDespatch)
        .values(
            notification_id=notification_id,
            despatched_on=despatched_on,
            cost_threshold=cost_threshold,
        )
        .on_conflict_do_update(
            index_elements=["notification_id"],
            set_={"despatched_on": despatched_on, "cost_threshold": cost_threshold.value},
        )
    )

    db.session.execute(stmt)
