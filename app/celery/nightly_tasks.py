from datetime import UTC, datetime, timedelta
from tempfile import TemporaryFile
from urllib.parse import urlencode
from uuid import UUID, uuid4

import boto3
import pyorc
from boto3.s3.transfer import TransferConfig
from flask import current_app
from notifications_utils.clients.zendesk.zendesk_client import (
    NotifySupportTicket,
    NotifyTicketType,
)
from notifications_utils.letter_timings import (
    get_dvla_working_day_offset_by,
    is_dvla_working_day,
)
from notifications_utils.timezones import convert_utc_to_bst
from sqlalchemy import delete, func, inspect, select
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
)
from app.dao.notifications_dao import (
    dao_get_notifications_processing_time_stats,
    dao_timeout_notifications,
    delete_test_notifications,
    get_service_ids_with_notifications_before,
    move_notifications_to_notification_history,
)
from app.dao.report_requests_dao import update_report_requests_status_to_deleted
from app.dao.service_data_retention_dao import (
    fetch_service_data_retention_for_all_services_by_notification_type,
)
from app.dao.unsubscribe_request_dao import (
    dao_archive_batched_unsubscribe_requests,
    dao_archive_old_unsubscribe_requests,
    get_service_ids_with_unsubscribe_requests,
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
        current_app.logger.info("Job ID %s has been removed from s3.", job.id, extra={"job_id": job.id})


@notify_celery.task(name="archive-unsubscribe-requests")
def archive_unsubscribe_requests():
    for service_id in get_service_ids_with_unsubscribe_requests():
        archive_batched_unsubscribe_requests.apply_async(queue=QueueNames.REPORTING, args=[service_id])
        archive_old_unsubscribe_requests.apply_async(queue=QueueNames.REPORTING, args=[service_id])


@notify_celery.task(name="archive-batched-unsubscribe-requests")
def archive_batched_unsubscribe_requests(service_id):
    start = datetime.now(UTC)
    count_deleted = dao_archive_batched_unsubscribe_requests(service_id)
    log_archive_unsubscribe_requests(start, service_id, count_deleted)


@notify_celery.task(name="archive-old-unsubscribe-requests")
def archive_old_unsubscribe_requests(service_id):
    start = datetime.now(UTC)
    count_deleted = dao_archive_old_unsubscribe_requests(service_id)
    log_archive_unsubscribe_requests(start, service_id, count_deleted)


def log_archive_unsubscribe_requests(start, service_id, count_deleted):
    base_params = {
        "celery_task": notify_celery.current_task.name,
        "service_id": service_id,
        "deleted_record_count": count_deleted,
        "duration": datetime.now(UTC) - start,
    }
    current_app.logger.info(
        "%(celery_task)s service: %(service_id)s, count deleted: %(deleted_record_count)s, duration: %(duration)s",
        base_params,
        extra={
            **base_params,
            "duration": base_params["duration"].total_seconds(),
        },
    )


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


def _delete_notifications_older_than_retention_by_type(
    notification_type,
    stagger_total_period=timedelta(minutes=5),
):
    flexible_data_retention = fetch_service_data_retention_for_all_services_by_notification_type(notification_type)

    for i, f in enumerate(flexible_data_retention):
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
            countdown=(i / len(flexible_data_retention)) * stagger_total_period.seconds,
        )

    seven_days_ago = get_london_midnight_in_utc(convert_utc_to_bst(datetime.utcnow()).date() - timedelta(days=7))
    service_ids_with_data_retention = {x.service_id for x in flexible_data_retention}

    # get a list of all service ids that we'll need to delete for. Typically that might only be 5% of services.
    # This query takes a couple of mins to run.
    service_ids_that_have_sent_notifications_recently = get_service_ids_with_notifications_before(
        notification_type, seven_days_ago
    )

    service_ids_to_purge = service_ids_that_have_sent_notifications_recently - service_ids_with_data_retention

    for i, service_id in enumerate(service_ids_to_purge):
        delete_notifications_for_service_and_type.apply_async(
            queue=QueueNames.REPORTING,
            kwargs={
                "service_id": service_id,
                "notification_type": notification_type,
                "datetime_to_delete_before": seven_days_ago,
            },
            countdown=(i / len(service_ids_to_purge)) * stagger_total_period.seconds,
        )

    extra = {
        "notification_type": notification_type,
        "service_ids_with_data_retention_count": len(service_ids_with_data_retention),
        "service_ids_to_purge_count": len(service_ids_to_purge),
    }
    current_app.logger.info(
        (
            "delete-notifications-older-than-retention: triggered subtasks for "
            "notification_type %(notification_type)s: "
            "%(service_ids_with_data_retention_count)s services with flexible data retention, "
            "%(service_ids_to_purge_count)s services without flexible data retention"
        ),
        extra,
        extra=extra,
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
        base_params = {
            "service_id": service_id,
            "notification_type": notification_type,
            "deleted_record_count": num_deleted,
            "duration": end - start,
        }
        current_app.logger.info(
            (
                "delete-notifications-for-service-and-type: "
                "service: %(service_id)s, notification_type: %(notification_type)s, "
                "count deleted: %(deleted_record_count)s, duration: %(duration)s"
            ),
            base_params,
            extra={
                **base_params,
                "duration": base_params["duration"].total_seconds(),
            },
        )
        # if some things were deleted, there could be more! lets queue up a new task with the same params
        # if there was nothing deleted, we've got no more work to do
        delete_notifications_for_service_and_type.apply_async(
            args=(service_id, notification_type, datetime_to_delete_before),
            queue=QueueNames.REPORTING,
        )
    else:
        # now we've deleted all the real notifications, clean up the test notifications
        delete_test_notifications_for_service_and_type.apply_async(
            args=(service_id, notification_type, datetime_to_delete_before),
            queue=QueueNames.REPORTING,
        )


@notify_celery.task(name="delete-test-notifications-for-service-and-type")
def delete_test_notifications_for_service_and_type(service_id, notification_type, datetime_to_delete_before):
    num_deleted = delete_test_notifications(notification_type, service_id, datetime_to_delete_before)

    if num_deleted:
        delete_test_notifications_for_service_and_type.apply_async(
            args=(service_id, notification_type, datetime_to_delete_before),
            queue=QueueNames.REPORTING,
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

        extra = {"notification_count": len(notifications)}
        current_app.logger.info(
            "Timeout period reached for %(notification_count)s notifications, status has been updated.",
            extra,
            extra=extra,
        )


@notify_celery.task(name="delete-inbound-sms")
@cronitor("delete-inbound-sms")
def delete_inbound_sms():
    try:
        start = datetime.utcnow()
        deleted = delete_inbound_sms_older_than_retention()
        base_params = {
            "start_time": start,
            "duration": datetime.utcnow() - start,
            "deleted_record_count": deleted,
        }
        current_app.logger.info(
            "Delete inbound sms job started %(start_time)s duration %(duration)s seconds deleted "
            "%(deleted_record_count)s inbound sms notifications",
            base_params,
            extra={
                **base_params,
                "duration": base_params["duration"].total_seconds(),
            },
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
                ticket_type=NotifySupportTicket.TYPE_TASK,
                notify_ticket_type=NotifyTicketType.TECHNICAL,
                notify_task_type="notify_task_letters_sending",
            )
            zendesk_client.send_ticket_to_zendesk(ticket)
        else:
            current_app.logger.error(
                "There are %s letters in the 'sending' state from %s",
                still_sending_count,
                sent_date.strftime("%A %d %B"),
                extra={"notification_count": still_sending_count, "sent_date": sent_date},
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
            # We pass datetimes as args to the next task but celery will actually call `isoformat` on these
            # and send them over as strings
            [start_datetime, end_datetime],
            # We use the reporting queue as it's not used for most of the day
            queue=QueueNames.REPORTING,
        )
        extra = {
            "start_time": start_datetime,
            "end_time": end_datetime,
        }
        current_app.logger.info(
            "Created delete_unneeded_notification_history_for_specific_hour task between "
            "%(start_time)s and %(end_time)s",
            extra,
            extra=extra,
        )
        start_datetime = end_datetime


@notify_celery.task(name="delete_unneeded_notification_history_for_specific_hour")
def delete_unneeded_notification_history_for_specific_hour(start_datetime: str, end_datetime: str):
    extra = {
        "start_time": start_datetime,
        "end_time": end_datetime,
    }
    current_app.logger.info(
        "Beginning delete_unneeded_notification_history_for_specific_hour between %(start_time)s and %(end_time)s",
        extra,
        extra=extra,
    )

    delete_notification_history_between_two_datetimes(start_datetime, end_datetime)


@notify_celery.task(name="update-report-status-to-deleted")
@cronitor("update-report-status-to-deleted")
def update_report_status_to_deleted():
    try:
        update_report_requests_status_to_deleted()
        current_app.logger.info("Successfully updated report status to deleted.")
    except SQLAlchemyError as e:
        current_app.logger.error("Failed to update report status to deleted: %s", str(e))
        raise


# in order of priority (type hierarchies can overlap!)
_python_types_orc_type_constructors = (
    (int, lambda: pyorc.Int()),
    (float, lambda: pyorc.Double()),
    (UUID, lambda: pyorc.Binary()),
    (str, lambda: pyorc.String()),
    (datetime, lambda: pyorc.Timestamp()),
    (bool, lambda: pyorc.Boolean()),
)


def _get_orc_type_from_python_type(python_type):
    for candidate_python_type, orc_type_ctr in _python_types_orc_type_constructors:
        if issubclass(python_type, candidate_python_type):
            return orc_type_ctr()

    raise ValueError(f"Don't know what orc type to use for python type {python_type!r}")


@notify_celery.task(name="deep-archive-notification-history-up-to-limit")
def deep_archive_notification_history_up_to_limit():
    delete_archived = current_app.config["NOTIFICATION_DEEP_HISTORY_DELETE_ARCHIVED"]
    max_hours_archived = current_app.config["NOTIFICATION_DEEP_HISTORY_MAX_HOURS_ARCHIVED_IN_RUN"]
    min_archivable_age = timedelta(days=current_app.config["NOTIFICATION_DEEP_HISTORY_MIN_AGE_DAYS"])
    earliest_unarchivable_datetime = (datetime.now(UTC) - min_archivable_age).replace(minute=0, second=0, microsecond=0)

    table = NotificationHistory.__table__

    latest_created_at_archived = None

    for _ in range(max_hours_archived):
        query = (
            select(table.c.created_at)
            .where(table.c.created_at < earliest_unarchivable_datetime)
            .order_by(table.c.created_at)
            .limit(1)
        )
        if latest_created_at_archived and not delete_archived:
            # extra clause needed to progress the run since rows aren't being deleted
            query = query.where(table.c.created_at > latest_created_at_archived)

        oldest_created_at_row = db.session.execute(query).scalars().all()
        if not oldest_created_at_row:
            current_app.logger.info("No more archivable notification_history rows")
            return

        oldest_created_at_hour = oldest_created_at_row[0].replace(minute=0, second=0, microsecond=0)
        oldest_created_at_hour_str = oldest_created_at_hour.isoformat()
        current_app.logger.info(
            "Archiving created_at hour beginning %s",
            oldest_created_at_hour_str,
            extra={"hour_beginning": oldest_created_at_hour_str},
        )

        latest_created_at_archived = _deep_archive_notification_history_hour_starting(oldest_created_at_hour)
    else:
        current_app.logger.info(
            "Archived maximum number of hours allowed in this run (%s)",
            max_hours_archived,
            extra={"max_hours_archived": max_hours_archived},
        )


def _deep_archive_notification_history_hour_starting(
    start_datetime: datetime,
    written_rows_log_every: int = 1_000_000,
) -> datetime:
    if start_datetime.minute or start_datetime.second or start_datetime.microsecond:
        raise ValueError(f"start_datetime {start_datetime!r} is not on-the-hour")

    end_datetime = start_datetime + timedelta(hours=1)

    s3_bucket = current_app.config["S3_BUCKET_NOTIFICATION_DEEP_HISTORY"]
    s3_key_prefix = current_app.config["NOTIFICATION_DEEP_HISTORY_S3_KEY_PREFIX"]
    delete_archived = current_app.config["NOTIFICATION_DEEP_HISTORY_DELETE_ARCHIVED"]

    s3 = boto3.client("s3")

    table = NotificationHistory.__table__
    orc_type_description = pyorc.Struct(
        **{col.name: _get_orc_type_from_python_type(col.type.python_type) for col in inspect(table).c}
    )

    latest_created_at = None

    with TemporaryFile() as f:
        with pyorc.Writer(
            f,
            orc_type_description,
            struct_repr=pyorc.StructRepr.DICT,
            compression=pyorc.CompressionKind.ZSTD,
            bloom_filter_columns=tuple(col.name for col in inspect(table).c if issubclass(col.type.python_type, UUID)),
        ) as writer:
            try:
                # hundreds of thousands of rows can occupy gigabytes of memory that this machine may not have
                db.session.connection().execution_options(stream_results=True, max_row_buffer=50_000)

                # here we take a share-lock on all our rows we intend to archive to ensure the
                # version we export is the *final* version the database saw. share-lock is taken
                # even if we're not deleting so that it simulates the performance impact of doing
                # it for real
                history_rows = db.session.execute(
                    select(table)
                    .where(
                        table.c.created_at >= start_datetime,
                        table.c.created_at < end_datetime,
                    )
                    .order_by(
                        table.c.created_at,
                        table.c.id,
                    )
                    .with_for_update(
                        read=True,
                    )
                ).all()

                for row in history_rows:
                    latest_created_at = row.created_at
                    writer.write({k: (v.bytes if isinstance(v, UUID) else v) for k, v in row._mapping.items()})
                    if not writer.current_row % written_rows_log_every:
                        current_app.logger.info(
                            "%s rows of ORC file written",
                            writer.current_row,
                            extra={"row_count": writer.current_row},
                        )

                final_current_row = writer.current_row
            finally:
                # connections configured to stream results must be used sparingly (and won't work for everything)
                db.session.connection().execution_options(stream_results=False)

        f.seek(0, 2)  # end of file
        final_file_size = f.tell()
        f.seek(0)

        current_app.logger.info(
            "Finished writing %s byte ORC file with %s rows",
            final_file_size,
            final_current_row,
            extra={
                "row_count": final_current_row,
                "file_size": final_file_size,
            },
        )

        s3_key = (
            f"{s3_key_prefix}"
            f"created_at_date_hour={start_datetime.date().isoformat()}T{start_datetime.hour:02}/"
            f"{uuid4()}.orc"
        )

        current_app.logger.info(
            "Uploading %s byte file to %s in bucket %s",
            final_file_size,
            s3_key,
            s3_bucket,
            extra={
                "s3_key": s3_key,
                "s3_bucket": s3_bucket,
                "file_size": final_file_size,
            },
        )

        s3.upload_fileobj(
            f,
            s3_bucket,
            s3_key,
            Config=TransferConfig(use_threads=False),
            ExtraArgs={
                "ServerSideEncryption": "AES256",
                "Tagging": urlencode({"contents_deleted": "false"}),
            },
        )

        current_app.logger.info(
            "Successfully uploaded %s to bucket %s",
            s3_key,
            s3_bucket,
            extra={
                "s3_key": s3_key,
                "s3_bucket": s3_bucket,
                "file_size": final_file_size,
            },
        )

        if delete_archived:
            # this will attempt to upgrade our share-locks to exclusive locks, waiting
            # until it is able to do so. in case of contention between two concurrent
            # tasks trying to delete the same rows, only one of the transactions will
            # be able to pass this point (due to the share-lock) and that one will
            # get to mark its uploaded archive as contents_deleted (thereby preventing
            # a lifecycle rule from reaping it). any other ones will have been killed
            # by the deadlock detector.
            deleted_row_count = db.session.execute(
                delete(table).where(
                    table.c.created_at >= start_datetime,
                    table.c.created_at < end_datetime,
                )
            ).rowcount

            if deleted_row_count != final_current_row:
                raise RuntimeError(
                    f"Number of deleted rows ({deleted_row_count}) would not be the same as "
                    f"number of rows exported ({final_current_row}) - cowardly refusing "
                    "to commit transaction"
                )

            db.session.commit()

            try:
                deleted_timestamp_iso = datetime.now(UTC).isoformat()

                current_app.logger.info(
                    "Tagging %s in bucket %s with contents_deleted=true, contents_deleted_at=%s",
                    s3_key,
                    s3_bucket,
                    deleted_timestamp_iso,
                    extra={
                        "s3_key": s3_key,
                        "s3_bucket": s3_bucket,
                        "file_size": final_file_size,
                    },
                )

                tag_set = s3.get_object_tagging(
                    Bucket=s3_bucket,
                    Key=s3_key,
                )["TagSet"]

                if existing_tag := next((tag for tag in tag_set if tag["Key"] == "contents_deleted_at"), None):
                    current_app.logger.warning(
                        "Found existing contents_deleted_at tag on object %s in bucket %s with value %s",
                        s3_key,
                        s3_bucket,
                        repr(existing_tag["Value"]),
                        extra={
                            "s3_key": s3_key,
                            "s3_bucket": s3_bucket,
                            "tag_value": existing_tag["Value"],
                        },
                    )
                if next((tag for tag in tag_set if tag["Key"] == "contents_deleted"), {}).get("Value") == "true":
                    current_app.logger.warning(
                        "Existing contents_deleted tag on object %s in bucket %s already has value 'true'",
                        s3_key,
                        s3_bucket,
                        extra={
                            "s3_key": s3_key,
                            "s3_bucket": s3_bucket,
                        },
                    )

                tag_set = [tag for tag in tag_set if tag["Key"] not in ("contents_deleted", "contents_deleted_at")]
                tag_set += [
                    {"Key": "contents_deleted", "Value": "true"},
                    {"Key": "contents_deleted_at", "Value": deleted_timestamp_iso},
                ]

                s3.put_object_tagging(
                    Bucket=s3_bucket,
                    Key=s3_key,
                    Tagging={
                        "TagSet": tag_set,
                    },
                )
            except Exception:
                current_app.logger.warning(
                    "Failed to tag archived notification file %s in bucket %s as contents_deleted=true, even "
                    "though the corresponding %s rows of NotificationHistory *were* successfully deleted - you "
                    "may need to manually find this s3 object and set this tag (note it may have been given a "
                    "delete marker by a lifecycle rule)",
                    s3_key,
                    s3_bucket,
                    deleted_row_count,
                    extra={
                        "s3_key": s3_key,
                        "s3_bucket": s3_bucket,
                        "deleted_row_count": deleted_row_count,
                        "file_size": final_file_size,
                    },
                )
                raise

            current_app.logger.info(
                "Successfully archived %s to bucket %s and deleted %s rows of NotificationHistory",
                s3_key,
                s3_bucket,
                deleted_row_count,
                extra={
                    "s3_key": s3_key,
                    "s3_bucket": s3_bucket,
                    "deleted_row_count": deleted_row_count,
                    "file_size": final_file_size,
                },
            )
        else:
            # release share-locks
            db.session.commit()

        return latest_created_at
