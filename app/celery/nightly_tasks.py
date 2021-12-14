from datetime import datetime, timedelta

import pytz
from flask import current_app
from notifications_utils.clients.zendesk.zendesk_client import (
    NotifySupportTicket,
)
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from app import notify_celery, zendesk_client
from app.aws import s3
from app.config import QueueNames
from app.cronitor import cronitor
from app.dao.fact_processing_time_dao import insert_update_processing_time
from app.dao.inbound_sms_dao import delete_inbound_sms_older_than_retention
from app.dao.jobs_dao import (
    dao_archive_job,
    dao_get_jobs_older_than_data_retention,
)
from app.dao.notifications_dao import (
    dao_get_notifications_processing_time_stats,
    dao_timeout_notifications,
    delete_notifications_older_than_retention_by_type,
)
from app.models import (
    EMAIL_TYPE,
    KEY_TYPE_NORMAL,
    LETTER_TYPE,
    NOTIFICATION_SENDING,
    SMS_TYPE,
    FactProcessingTime,
    Notification,
)
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
        current_app.logger.info("Job ID {} has been removed from s3.".format(job.id))


@notify_celery.task(name="delete-notifications-older-than-retention")
def delete_notifications_older_than_retention():
    delete_email_notifications_older_than_retention.apply_async(queue=QueueNames.REPORTING)
    delete_sms_notifications_older_than_retention.apply_async(queue=QueueNames.REPORTING)
    delete_letter_notifications_older_than_retention.apply_async(queue=QueueNames.REPORTING)


@notify_celery.task(name="delete-sms-notifications")
@cronitor("delete-sms-notifications")
def delete_sms_notifications_older_than_retention():
    start = datetime.utcnow()
    deleted = delete_notifications_older_than_retention_by_type('sms')
    current_app.logger.info(
        "Delete {} job started {} finished {} deleted {} sms notifications".format(
            'sms',
            start,
            datetime.utcnow(),
            deleted
        )
    )


@notify_celery.task(name="delete-email-notifications")
@cronitor("delete-email-notifications")
def delete_email_notifications_older_than_retention():
    start = datetime.utcnow()
    deleted = delete_notifications_older_than_retention_by_type('email')
    current_app.logger.info(
        "Delete {} job started {} finished {} deleted {} email notifications".format(
            'email',
            start,
            datetime.utcnow(),
            deleted
        )
    )


@notify_celery.task(name="delete-letter-notifications")
@cronitor("delete-letter-notifications")
def delete_letter_notifications_older_than_retention():
    start = datetime.utcnow()
    deleted = delete_notifications_older_than_retention_by_type('letter')
    current_app.logger.info(
        "Delete {} job started {} finished {} deleted {} letter notifications".format(
            'letter',
            start,
            datetime.utcnow(),
            deleted
        )
    )


@notify_celery.task(name='timeout-sending-notifications')
@cronitor('timeout-sending-notifications')
def timeout_notifications():
    notifications = ['dummy value so len() > 0']

    cutoff_time = datetime.utcnow() - timedelta(
        seconds=current_app.config.get('SENDING_NOTIFICATIONS_TIMEOUT_PERIOD')
    )

    while len(notifications) > 0:
        notifications = dao_timeout_notifications(cutoff_time)

        for notification in notifications:
            check_and_queue_callback_task(notification)

        current_app.logger.info(
            "Timeout period reached for {} notifications, status has been updated.".format(len(notifications)))


@notify_celery.task(name="delete-inbound-sms")
@cronitor("delete-inbound-sms")
def delete_inbound_sms():
    try:
        start = datetime.utcnow()
        deleted = delete_inbound_sms_older_than_retention()
        current_app.logger.info(
            "Delete inbound sms job started {} finished {} deleted {} inbound sms notifications".format(
                start,
                datetime.utcnow(),
                deleted
            )
        )
    except SQLAlchemyError:
        current_app.logger.exception("Failed to delete inbound sms notifications")
        raise


@notify_celery.task(name="raise-alert-if-letter-notifications-still-sending")
@cronitor("raise-alert-if-letter-notifications-still-sending")
def raise_alert_if_letter_notifications_still_sending():
    still_sending_count, sent_date = get_letter_notifications_still_sending_when_they_shouldnt_be()

    if still_sending_count:
        message = "There are {} letters in the 'sending' state from {}".format(
            still_sending_count,
            sent_date.strftime('%A %d %B')
        )
        # Only send alerts in production
        if current_app.config['NOTIFY_ENVIRONMENT'] in ['live', 'production', 'test']:
            message += ". Resolve using https://github.com/alphagov/notifications-manuals/wiki/Support-Runbook#deal-with-letters-still-in-sending"  # noqa

            ticket = NotifySupportTicket(
                subject=f"[{current_app.config['NOTIFY_ENVIRONMENT']}] Letters still sending",
                email_ccs=current_app.config['DVLA_EMAIL_ADDRESSES'],
                message=message,
                ticket_type=NotifySupportTicket.TYPE_INCIDENT,
                technical_ticket=True,
                ticket_categories=['notify_letters']
            )
            zendesk_client.send_ticket_to_zendesk(ticket)
        else:
            current_app.logger.info(message)


def get_letter_notifications_still_sending_when_they_shouldnt_be():
    today = datetime.utcnow().date()

    # Do nothing on the weekend
    if today.isoweekday() in {6, 7}:  # sat, sun
        return 0, None

    if today.isoweekday() in {1, 2}:  # mon, tues. look for files from before the weekend
        offset_days = 4
    else:
        offset_days = 2

    expected_sent_date = today - timedelta(days=offset_days)

    q = Notification.query.filter(
        Notification.notification_type == LETTER_TYPE,
        Notification.status == NOTIFICATION_SENDING,
        Notification.key_type == KEY_TYPE_NORMAL,
        func.date(Notification.sent_at) <= expected_sent_date
    )

    return q.count(), expected_sent_date


@notify_celery.task(name='raise-alert-if-no-letter-ack-file')
@cronitor('raise-alert-if-no-letter-ack-file')
def letter_raise_alert_if_no_ack_file_for_zip():
    # get a list of zip files since yesterday
    zip_file_set = set()
    today_str = datetime.utcnow().strftime('%Y-%m-%d')
    yesterday = datetime.now(tz=pytz.utc) - timedelta(days=1)  # AWS datetime format

    for key in s3.get_list_of_files_by_suffix(bucket_name=current_app.config['LETTERS_PDF_BUCKET_NAME'],
                                              subfolder=today_str + '/zips_sent',
                                              suffix='.TXT'):
        subname = key.split('/')[-1]  # strip subfolder in name
        zip_file_set.add(subname.upper().replace('.ZIP.TXT', ''))

    # get acknowledgement file
    ack_file_set = set()

    for key in s3.get_list_of_files_by_suffix(bucket_name=current_app.config['DVLA_RESPONSE_BUCKET_NAME'],
                                              subfolder='root/dispatch', suffix='.ACK.txt', last_modified=yesterday):
        ack_file_set.add(key.lstrip('root/dispatch').upper().replace('.ACK.TXT', ''))

    message = '\n'.join([
        "Letter ack file does not contain all zip files sent."
        "",
        f"See runbook at https://github.com/alphagov/notifications-manuals/wiki/Support-Runbook#letter-ack-file-does-not-contain-all-zip-files-sent\n",  # noqa
        f"pdf bucket: {current_app.config['LETTERS_PDF_BUCKET_NAME']}, subfolder: {datetime.utcnow().strftime('%Y-%m-%d')}/zips_sent",  # noqa
        f"ack bucket: {current_app.config['DVLA_RESPONSE_BUCKET_NAME']}",
        "",
        f"Missing ack for zip files: {str(sorted(zip_file_set - ack_file_set))}",
    ])

    # strip empty element before comparison
    ack_file_set.discard('')
    zip_file_set.discard('')

    if len(zip_file_set - ack_file_set) > 0:
        if current_app.config['NOTIFY_ENVIRONMENT'] in ['live', 'production', 'test']:
            ticket = NotifySupportTicket(
                subject="Letter acknowledge error",
                message=message,
                ticket_type=NotifySupportTicket.TYPE_INCIDENT,
                technical_ticket=True,
                ticket_categories=['notify_letters']
            )
            zendesk_client.send_ticket_to_zendesk(ticket)
        current_app.logger.error(message)

    if len(ack_file_set - zip_file_set) > 0:
        current_app.logger.info(
            "letter ack contains zip that is not for today: {}".format(ack_file_set - zip_file_set)
        )


@notify_celery.task(name='save-daily-notification-processing-time')
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
            messages_within_10_secs=result.messages_within_10_secs
        )
    )
