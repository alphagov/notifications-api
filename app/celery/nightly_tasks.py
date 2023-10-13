from datetime import datetime, timedelta

import dateutil
import pytz
from flask import current_app
from notifications_utils.clients.zendesk.zendesk_client import (
    NotifySupportTicket,
    NotifyTicketType,
)
from notifications_utils.letter_timings import (
    get_dvla_working_day_offset_by,
    is_dvla_working_day,
)
from notifications_utils.timezones import convert_bst_to_utc, convert_utc_to_bst
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from app import db, notify_celery, statsd_client, zendesk_client
from app.aws import s3
from app.config import QueueNames
from app.constants import (
    EMAIL_TYPE,
    KEY_TYPE_NORMAL,
    LETTER_TYPE,
    NOTIFICATION_SENDING,
    SMS_TYPE,
)
from app.cronitor import cronitor
from app.dao.fact_processing_time_dao import insert_update_processing_time
from app.dao.inbound_sms_dao import delete_inbound_sms_older_than_retention
from app.dao.jobs_dao import (
    dao_archive_job,
    dao_get_jobs_older_than_data_retention,
)
from app.dao.notification_history_dao import (
    delete_notification_history_between_two_datetimes,
    delete_notification_history_older_than_datetime,
)
from app.dao.notifications_dao import (
    dao_get_notifications_processing_time_stats,
    dao_timeout_notifications,
    get_service_ids_with_notifications_before,
    move_notifications_to_notification_history,
)
from app.dao.service_data_retention_dao import (
    fetch_service_data_retention_for_all_services_by_notification_type,
)
from app.models import FactProcessingTime, Notification, NotificationHistory
from app.notifications.notifications_ses_callback import (
    check_and_queue_callback_task,
)
from app.utils import get_london_midnight_in_utc


@notify_celery.task(name="remove_sms_email_jobs")
@cronitor("remove_sms_email_jobs")
def remove_sms_email_csv_files():
    _remove_csv_files([EMAIL_TYPE, SMS_TYPE])


@notify_celery.task(name="remove_letter_jobs")
@cronitor("remove_letter_jobs")
def remove_letter_csv_files():
    _remove_csv_files([LETTER_TYPE])


def _remove_csv_files(job_types):
    jobs = dao_get_jobs_older_than_data_retention(notification_types=job_types)
    for job in jobs:
        s3.remove_job_from_s3(job.service_id, job.id)
        dao_archive_job(job)
        current_app.logger.info("Job ID %s has been removed from s3.", job.id)


@notify_celery.task(name="delete-notifications-older-than-retention")
def delete_notifications_older_than_retention():
    delete_email_notifications_older_than_retention.apply_async(queue=QueueNames.REPORTING)
    delete_sms_notifications_older_than_retention.apply_async(queue=QueueNames.REPORTING)
    delete_letter_notifications_older_than_retention.apply_async(queue=QueueNames.REPORTING)


@notify_celery.task(name="delete-sms-notifications")
@cronitor("delete-sms-notifications")
def delete_sms_notifications_older_than_retention():
    _delete_notifications_older_than_retention_by_type("sms")


@notify_celery.task(name="delete-email-notifications")
@cronitor("delete-email-notifications")
def delete_email_notifications_older_than_retention():
    _delete_notifications_older_than_retention_by_type("email")


@notify_celery.task(name="delete-letter-notifications")
@cronitor("delete-letter-notifications")
def delete_letter_notifications_older_than_retention():
    _delete_notifications_older_than_retention_by_type("letter")


def _delete_notifications_older_than_retention_by_type(notification_type):
    flexible_data_retention = fetch_service_data_retention_for_all_services_by_notification_type(notification_type)

    for f in flexible_data_retention:
        day_to_delete_backwards_from = get_london_midnight_in_utc(
            convert_utc_to_bst(datetime.utcnow()).date() - timedelta(days=f.days_of_retention)
        )

        delete_notifications_for_service_and_type.apply_async(
            queue=QueueNames.REPORTING,
            kwargs={
                "service_id": f.service_id,
                "notification_type": notification_type,
                "datetime_to_delete_before": day_to_delete_backwards_from,
            },
        )

    seven_days_ago = get_london_midnight_in_utc(convert_utc_to_bst(datetime.utcnow()).date() - timedelta(days=7))
    service_ids_with_data_retention = {x.service_id for x in flexible_data_retention}

    # get a list of all service ids that we'll need to delete for. Typically that might only be 5% of services.
    # This query takes a couple of mins to run.
    service_ids_that_have_sent_notifications_recently = get_service_ids_with_notifications_before(
        notification_type, seven_days_ago
    )

    service_ids_to_purge = service_ids_that_have_sent_notifications_recently - service_ids_with_data_retention

    for service_id in service_ids_to_purge:
        delete_notifications_for_service_and_type.apply_async(
            queue=QueueNames.REPORTING,
            kwargs={
                "service_id": service_id,
                "notification_type": notification_type,
                "datetime_to_delete_before": seven_days_ago,
            },
        )

    current_app.logger.info(
        (
            "delete-notifications-older-than-retention: triggered subtasks for notification_type %(type)s: "
            "%(num_service_ids_with_data_retention)s services with flexible data retention, "
            "%(num_service_ids_to_purge)s services without flexible data retention"
        ),
        dict(
            type=notification_type,
            num_service_ids_with_data_retention=len(service_ids_with_data_retention),
            num_service_ids_to_purge=len(service_ids_to_purge),
        ),
    )


@notify_celery.task(name="delete-notifications-for-service-and-type")
def delete_notifications_for_service_and_type(service_id, notification_type, datetime_to_delete_before):
    start = datetime.utcnow()
    num_deleted = move_notifications_to_notification_history(
        notification_type,
        service_id,
        datetime_to_delete_before,
    )
    if num_deleted:
        end = datetime.utcnow()
        current_app.logger.info(
            (
                "delete-notifications-for-service-and-type: "
                "service: %(service_id)s, notification_type: %(type)s, "
                "count deleted: %(num_deleted)s, duration: %(duration)s seconds"
            ),
            dict(
                service_id=service_id, type=notification_type, num_deleted=num_deleted, duration=(end - start).seconds
            ),
        )


@notify_celery.task(name="timeout-sending-notifications")
@cronitor("timeout-sending-notifications")
def timeout_notifications():
    notifications = ["dummy value so len() > 0"]

    cutoff_time = datetime.utcnow() - timedelta(seconds=current_app.config.get("SENDING_NOTIFICATIONS_TIMEOUT_PERIOD"))

    while len(notifications) > 0:
        notifications = dao_timeout_notifications(cutoff_time)

        for notification in notifications:
            statsd_client.incr(f"timeout-sending.{notification.sent_by}")
            check_and_queue_callback_task(notification)

        current_app.logger.info(
            "Timeout period reached for %s notifications, status has been updated.", len(notifications)
        )


@notify_celery.task(name="delete-inbound-sms")
@cronitor("delete-inbound-sms")
def delete_inbound_sms():
    try:
        start = datetime.utcnow()
        deleted = delete_inbound_sms_older_than_retention()
        current_app.logger.info(
            "Delete inbound sms job started %(start)s finished %(now)s deleted %(deleted)s inbound sms notifications",
            dict(start=start, now=datetime.utcnow(), deleted=deleted),
        )
    except SQLAlchemyError:
        current_app.logger.exception("Failed to delete inbound sms notifications")
        raise


@notify_celery.task(name="raise-alert-if-letter-notifications-still-sending")
@cronitor("raise-alert-if-letter-notifications-still-sending")
def raise_alert_if_letter_notifications_still_sending():
    still_sending_count, sent_date = get_letter_notifications_still_sending_when_they_shouldnt_be()

    if still_sending_count:

        if current_app.should_send_zendesk_alerts:
            message = (
                f"There are {still_sending_count} letters in the 'sending' state from {sent_date.strftime('%A %d %B')}."
                " Resolve using https://github.com/alphagov/notifications-manuals/wiki"
                "/Support-Runbook#deal-with-letters-still-in-sending"
            )

            ticket = NotifySupportTicket(
                subject=f"[{current_app.config['NOTIFY_ENVIRONMENT']}] Letters still sending",
                email_ccs=current_app.config["DVLA_EMAIL_ADDRESSES"],
                message=message,
                ticket_type=NotifySupportTicket.TYPE_INCIDENT,
                notify_ticket_type=NotifyTicketType.TECHNICAL,
                ticket_categories=["notify_letters"],
            )
            zendesk_client.send_ticket_to_zendesk(ticket)
        else:
            current_app.logger.error(
                "There are %s letters in the 'sending' state from %s",
                still_sending_count,
                sent_date.strftime("%A %d %B"),
            )


def get_letter_notifications_still_sending_when_they_shouldnt_be():
    now = datetime.utcnow()

    # If it's a weekend day or a bank holiday, do nothing
    if not is_dvla_working_day(now):
        return 0, None

    expected_sent_date = get_dvla_working_day_offset_by(now, days=-2).date()

    q = Notification.query.filter(
        Notification.notification_type == LETTER_TYPE,
        Notification.status == NOTIFICATION_SENDING,
        Notification.key_type == KEY_TYPE_NORMAL,
        func.date(Notification.sent_at) <= expected_sent_date,
    )

    return q.count(), expected_sent_date


@notify_celery.task(name="raise-alert-if-no-letter-ack-file")
@cronitor("raise-alert-if-no-letter-ack-file")
def letter_raise_alert_if_no_ack_file_for_zip():
    # get a list of zip files since yesterday
    zip_file_set = set()
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    yesterday = datetime.now(tz=pytz.utc) - timedelta(days=1)  # AWS datetime format

    for key in s3.get_list_of_files_by_suffix(
        bucket_name=current_app.config["S3_BUCKET_LETTERS_PDF"], subfolder=today_str + "/zips_sent", suffix=".TXT"
    ):
        subname = key.split("/")[-1]  # strip subfolder in name
        zip_file_set.add(subname.upper().replace(".ZIP.TXT", ""))

    # get acknowledgement file
    ack_file_set = set()

    for key in s3.get_list_of_files_by_suffix(
        bucket_name=current_app.config["S3_BUCKET_DVLA_RESPONSE"],
        subfolder="root/dispatch",
        suffix=".ACK.txt",
        last_modified=yesterday,
    ):
        ack_file_set.add(key.lstrip("root/dispatch").upper().replace(".ACK.TXT", ""))  # noqa

    # strip empty element before comparison
    ack_file_set.discard("")
    zip_file_set.discard("")

    message = (
        "Letter ack file does not contain all zip files sent. See runbook at "
        "https://github.com/alphagov/notifications-manuals/wiki"
        "/Support-Runbook#letter-ack-file-does-not-contain-all-zip-files-sent\n\n"
        f"pdf bucket: {current_app.config['S3_BUCKET_LETTERS_PDF']}, "
        f"subfolder: {datetime.utcnow().strftime('%Y-%m-%d')}/zips_sent\n"
        f"ack bucket: {current_app.config['S3_BUCKET_DVLA_RESPONSE']}\n\n"
        f"Missing ack for zip files: {str(sorted(zip_file_set - ack_file_set))}"
    )

    if len(zip_file_set - ack_file_set) > 0:
        if current_app.should_send_zendesk_alerts:
            ticket = NotifySupportTicket(
                subject="Letter acknowledge error",
                message=message,
                ticket_type=NotifySupportTicket.TYPE_INCIDENT,
                notify_ticket_type=NotifyTicketType.TECHNICAL,
                ticket_categories=["notify_letters"],
            )
            zendesk_client.send_ticket_to_zendesk(ticket)

        current_app.logger.error(
            "Letter ack file does not contain all zip files sent.",
            extra=dict(
                pdf_bucket=current_app.config["S3_BUCKET_LETTERS_PDF"],
                subfolder=datetime.utcnow().strftime("%Y-%m-%d") + "/zips_sent",
                ack_bucket=current_app.config["S3_BUCKET_DVLA_RESPONSE"],
                missing_ack_for_zip_files=str(sorted(zip_file_set - ack_file_set)),
            ),
        )

    if len(ack_file_set - zip_file_set) > 0:
        current_app.logger.info("letter ack contains zip that is not for today: %s", ack_file_set - zip_file_set)


@notify_celery.task(name="save-daily-notification-processing-time")
@cronitor("save-daily-notification-processing-time")
def save_daily_notification_processing_time(bst_date=None):
    # bst_date is a string in the format of "YYYY-MM-DD"
    if bst_date is None:
        # if a date is not provided, we run against yesterdays data
        bst_date = (datetime.utcnow() - timedelta(days=1)).date()
    else:
        bst_date = datetime.strptime(bst_date, "%Y-%m-%d").date()

    start_time = get_london_midnight_in_utc(bst_date)
    end_time = get_london_midnight_in_utc(bst_date + timedelta(days=1))
    result = dao_get_notifications_processing_time_stats(start_time, end_time)
    insert_update_processing_time(
        FactProcessingTime(
            bst_date=bst_date,
            messages_total=result.messages_total,
            messages_within_10_secs=result.messages_within_10_secs,
        )
    )


@notify_celery.task(name="delete-oldest-quarter-of-unneeded-notification-history")
def delete_oldest_quarter_of_unneeded_notification_history():
    # This function will delete either 1 or 0 quarters of notifications from the notification_history
    # table. It will pick the oldest quarter available before our retention limit and delete that.
    # If there are no notifications older than our retention limit, then it won't do anything.
    # By running this task several nights in a row, it will slowly delete a quarter of notification_history
    # per night until we reach out retention limit
    #
    # We do everything in this function in BST up until the final point
    # This is because we care about quarters in the BST timezone because this is
    # how we bill our users and is easier to reason about.
    # When we finally figure out which BST quarter we can delete, we convert the time
    # to UTC so that we delete the correct notifications from our database
    #
    # This retention limit is hardcoded and was originally picked from
    # https://github.com/alphagov/notifications-aws/blob/main/decisions/2022-12-01-notification-history-retention-period.md
    # It was supposed to be 2023-4-1.
    # However, at the time of writing this code we realised the FtBillingLetterDispatch table has been introduced
    # which means we need to store letters older than 2023-4-1 in order to rebuild that table (because that table
    # uses the date of dispatch, not the date of creation for which date to bill for). To keep it simple, we keep
    # an extra quarters worth of data giving us plenty of buffer
    #
    # In the future, we will be able to update this retention_limit_bst value when we have progressed 3 quarters
    # into the next financial year
    current_app.logger.info("Beginning celery task delete_oldest_quarter_of_unneeded_notification_history")

    if current_app.config["NOTIFY_ENVIRONMENT"] == "staging":
        # We don't want to run this in staging as we want to keep some older notifications in there for migration
        # testing
        # After we've migrated our database, we should be able to remove this check and let this run in staging
        current_app.logger.info(
            "Aborting delete_oldest_quarter_of_unneeded_notification_history as staging environment"
        )
        return

    retention_limit_bst = datetime(2023, 1, 1)

    oldest_notification_utc = db.session.query(func.min(NotificationHistory.created_at)).one()[0]
    current_app.logger.info("Oldest notification in notification_history found is %s UTC", oldest_notification_utc)
    oldest_notification_bst = convert_utc_to_bst(oldest_notification_utc)
    if oldest_notification_bst >= retention_limit_bst:
        current_app.logger.info(
            "No notifications older than retention date of %s so nothing to delete", retention_limit_bst
        )
        return

    deletion_date_bst = pick_bst_quarter_to_delete_back_from(oldest_notification_bst)

    # in case there is an error in our logic above, let us just double check that we aren't trying to delete for
    # anything after our retention limit
    if deletion_date_bst > retention_limit_bst:
        raise Exception("Attempted to delete past our notification_history retention limit")

    deletion_date_utc = convert_bst_to_utc(deletion_date_bst)

    delete_notification_history_older_than_datetime(deletion_date_utc)


def pick_bst_quarter_to_delete_back_from(oldest_notification_bst):
    # We've picked a potential deletion date to start that we know is older than the oldest notification
    # in notification_history at the time of writing this code.
    # The potential deletion date to start is intentionally the BST start of a new quarter
    deletion_date = datetime(2019, 10, 1)
    while deletion_date <= oldest_notification_bst:
        # There are no notifications older than our deletion date, lets add 3 months
        # and see if that is still true
        # When we finally find a deletion date that has notifications older than the deletion date
        # we can then delete anything older (ie the previous quarters data)
        deletion_date = deletion_date + dateutil.relativedelta.relativedelta(months=3)

    return deletion_date


@notify_celery.task(name="delete_unneeded_notification_history_by_hour")
def delete_unneeded_notification_history_by_hour():
    # This task will delete all of the notification_history table older than 1 Jan 2023 BST
    #
    # This task will create lots of tasks, each one responsible for deleting a particular hour of
    # notification_history that is no longer needed
    #
    # This retention limit is hardcoded and was originally picked from
    # https://github.com/alphagov/notifications-aws/blob/main/decisions/2022-12-01-notification-history-retention-period.md
    # It was supposed to be 2023-4-1.
    # However, at the time of writing this code we realised the FtBillingLetterDispatch table has been introduced
    # which means we need to store letters older than 2023-4-1 in order to rebuild that table (because that table
    # uses the date of dispatch, not the date of creation for which date to bill for). To keep it simple, we keep
    # an extra quarters worth of data giving us plenty of buffer
    #
    # In the future, we will be able to update this retention_limit value when we have progressed 3 quarters
    # into the next financial year
    #
    # Arbitrary start_datetime, just slightly older than the oldest notification in the notification_history
    # table at the time of writing
    start_datetime = datetime(2020, 8, 1, 0, 0, 0)
    retention_limit = datetime(2023, 1, 1, 0, 0, 0)

    while start_datetime < retention_limit:
        end_datetime = start_datetime + timedelta(hours=1)
        delete_unneeded_notification_history_for_specific_hour.apply_async(
            [start_datetime, end_datetime],
            # We use the broadcasts queue temporarily as it pulled from by a worker doing no work
            # We don't want to put the tasks on the periodic queue because they make take up all
            # the workers capacity, stopping other important tasks from happening
            queue=QueueNames.BROADCASTS,
        )
        current_app.logger.info(
            "Created delete_unneeded_notification_history_for_specific_hour task between %s and %s",
            start_datetime,
            end_datetime,
        )
        start_datetime = end_datetime


@notify_celery.task(name="delete_unneeded_notification_history_for_specific_hour")
def delete_unneeded_notification_history_for_specific_hour(start_datetime, end_datetime):
    current_app.logger.info(
        "Beginning delete_unneeded_notification_history_for_specific_hour between %s and %s",
        start_datetime,
        end_datetime,
    )

    delete_notification_history_between_two_datetimes(start_datetime, end_datetime)
