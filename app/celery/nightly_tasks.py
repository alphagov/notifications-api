from datetime import (
    datetime,
    timedelta
)

import pytz
from flask import current_app
from notifications_utils.statsd_decorators import statsd
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from app import notify_celery, performance_platform_client, zendesk_client
from app.aws import s3
from app.celery.service_callback_tasks import (
    send_delivery_status_to_service,
    create_delivery_status_callback_data,
)
from app.config import QueueNames
from app.dao.inbound_sms_dao import delete_inbound_sms_older_than_retention
from app.dao.jobs_dao import (
    dao_get_jobs_older_than_data_retention,
    dao_archive_job
)
from app.dao.notifications_dao import (
    dao_timeout_notifications,
    delete_notifications_older_than_retention_by_type,
)
from app.dao.service_callback_api_dao import get_service_delivery_status_callback_api_for_service
from app.exceptions import NotificationTechnicalFailureException
from app.models import (
    Notification,
    NOTIFICATION_SENDING,
    EMAIL_TYPE,
    SMS_TYPE,
    LETTER_TYPE,
    KEY_TYPE_NORMAL
)
from app.performance_platform import total_sent_notifications, processing_time
from app.cronitor import cronitor
from app.utils import get_london_midnight_in_utc


@notify_celery.task(name="remove_sms_email_jobs")
@cronitor("remove_sms_email_jobs")
@statsd(namespace="tasks")
def remove_sms_email_csv_files():
    _remove_csv_files([EMAIL_TYPE, SMS_TYPE])


@notify_celery.task(name="remove_letter_jobs")
@cronitor("remove_letter_jobs")
@statsd(namespace="tasks")
def remove_letter_csv_files():
    _remove_csv_files([LETTER_TYPE])


def _remove_csv_files(job_types):
    jobs = dao_get_jobs_older_than_data_retention(notification_types=job_types)
    for job in jobs:
        s3.remove_job_from_s3(job.service_id, job.id)
        dao_archive_job(job)
        current_app.logger.info("Job ID {} has been removed from s3.".format(job.id))


@notify_celery.task(name="delete-sms-notifications")
@cronitor("delete-sms-notifications")
@statsd(namespace="tasks")
def delete_sms_notifications_older_than_retention():
    try:
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
    except SQLAlchemyError:
        current_app.logger.exception("Failed to delete sms notifications")
        raise


@notify_celery.task(name="delete-email-notifications")
@cronitor("delete-email-notifications")
@statsd(namespace="tasks")
def delete_email_notifications_older_than_retention():
    try:
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
    except SQLAlchemyError:
        current_app.logger.exception("Failed to delete email notifications")
        raise


@notify_celery.task(name="delete-letter-notifications")
@cronitor("delete-letter-notifications")
@statsd(namespace="tasks")
def delete_letter_notifications_older_than_retention():
    try:
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
    except SQLAlchemyError:
        current_app.logger.exception("Failed to delete letter notifications")
        raise


@notify_celery.task(name='timeout-sending-notifications')
@cronitor('timeout-sending-notifications')
@statsd(namespace="tasks")
def timeout_notifications():
    technical_failure_notifications, temporary_failure_notifications = \
        dao_timeout_notifications(current_app.config.get('SENDING_NOTIFICATIONS_TIMEOUT_PERIOD'))

    notifications = technical_failure_notifications + temporary_failure_notifications
    for notification in notifications:
        # queue callback task only if the service_callback_api exists
        service_callback_api = get_service_delivery_status_callback_api_for_service(service_id=notification.service_id)
        if service_callback_api:
            encrypted_notification = create_delivery_status_callback_data(notification, service_callback_api)
            send_delivery_status_to_service.apply_async([str(notification.id), encrypted_notification],
                                                        queue=QueueNames.CALLBACKS)

    current_app.logger.info(
        "Timeout period reached for {} notifications, status has been updated.".format(len(notifications)))
    if technical_failure_notifications:
        message = "{} notifications have been updated to technical-failure because they " \
                  "have timed out and are still in created.Notification ids: {}".format(
                      len(technical_failure_notifications), [str(x.id) for x in technical_failure_notifications])
        raise NotificationTechnicalFailureException(message)


@notify_celery.task(name='send-daily-performance-platform-stats')
@cronitor('send-daily-performance-platform-stats')
@statsd(namespace="tasks")
def send_daily_performance_platform_stats(date=None):
    # date is a string in the format of "YYYY-MM-DD"
    if date is None:
        date = (datetime.utcnow() - timedelta(days=1)).date()
    else:
        date = datetime.strptime(date, "%Y-%m-%d").date()

    if performance_platform_client.active:

        send_total_sent_notifications_to_performance_platform(bst_date=date)
        processing_time.send_processing_time_to_performance_platform(bst_date=date)


def send_total_sent_notifications_to_performance_platform(bst_date):
    count_dict = total_sent_notifications.get_total_sent_notifications_for_day(bst_date)
    start_time = get_london_midnight_in_utc(bst_date)

    email_sent_count = count_dict['email']
    sms_sent_count = count_dict['sms']
    letter_sent_count = count_dict['letter']

    current_app.logger.info(
        "Attempting to update Performance Platform for {} with {} emails, {} text messages and {} letters"
        .format(bst_date, email_sent_count, sms_sent_count, letter_sent_count)
    )

    total_sent_notifications.send_total_notifications_sent_for_day_stats(
        start_time,
        'sms',
        sms_sent_count
    )

    total_sent_notifications.send_total_notifications_sent_for_day_stats(
        start_time,
        'email',
        email_sent_count
    )

    total_sent_notifications.send_total_notifications_sent_for_day_stats(
        start_time,
        'letter',
        letter_sent_count
    )


@notify_celery.task(name="delete-inbound-sms")
@cronitor("delete-inbound-sms")
@statsd(namespace="tasks")
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


# TODO: remove me, i'm not being run by anything
@notify_celery.task(name="delete_dvla_response_files")
@statsd(namespace="tasks")
def delete_dvla_response_files_older_than_seven_days():
    try:
        start = datetime.utcnow()
        bucket_objects = s3.get_s3_bucket_objects(
            current_app.config['DVLA_RESPONSE_BUCKET_NAME'],
            'root/dispatch'
        )
        older_than_seven_days = s3.filter_s3_bucket_objects_within_date_range(bucket_objects)

        for f in older_than_seven_days:
            s3.remove_s3_object(current_app.config['DVLA_RESPONSE_BUCKET_NAME'], f['Key'])

        current_app.logger.info(
            "Delete dvla response files started {} finished {} deleted {} files".format(
                start,
                datetime.utcnow(),
                len(older_than_seven_days)
            )
        )
    except SQLAlchemyError:
        current_app.logger.exception("Failed to delete dvla response files")
        raise


@notify_celery.task(name="raise-alert-if-letter-notifications-still-sending")
@cronitor("raise-alert-if-letter-notifications-still-sending")
@statsd(namespace="tasks")
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
            zendesk_client.create_ticket(
                subject="[{}] Letters still sending".format(current_app.config['NOTIFY_ENVIRONMENT']),
                message=message,
                ticket_type=zendesk_client.TYPE_INCIDENT
            )
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

    if today.isoweekday() in {2, 4}:  # on tue, thu, we only care about first class letters
        q = q.filter(
            Notification.postage == 'first'
        )

    return q.count(), expected_sent_date


@notify_celery.task(name='raise-alert-if-no-letter-ack-file')
@cronitor('raise-alert-if-no-letter-ack-file')
@statsd(namespace="tasks")
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

    message = (
        "Letter ack file does not contain all zip files sent. "
        "Missing ack for zip files: {}, "
        "pdf bucket: {}, subfolder: {}, "
        "ack bucket: {}"
    ).format(
        str(sorted(zip_file_set - ack_file_set)),
        current_app.config['LETTERS_PDF_BUCKET_NAME'],
        datetime.utcnow().strftime('%Y-%m-%d') + '/zips_sent',
        current_app.config['DVLA_RESPONSE_BUCKET_NAME']
    )
    # strip empty element before comparison
    ack_file_set.discard('')
    zip_file_set.discard('')

    if len(zip_file_set - ack_file_set) > 0:
        if current_app.config['NOTIFY_ENVIRONMENT'] in ['live', 'production', 'test']:
            zendesk_client.create_ticket(
                subject="Letter acknowledge error",
                message=message,
                ticket_type=zendesk_client.TYPE_INCIDENT
            )
        current_app.logger.error(message)

    if len(ack_file_set - zip_file_set) > 0:
        current_app.logger.info(
            "letter ack contains zip that is not for today: {}".format(ack_file_set - zip_file_set)
        )
