from datetime import (
    date,
    datetime,
    timedelta
)

import pytz
from flask import current_app
from notifications_utils.statsd_decorators import statsd
from sqlalchemy import and_, func
from sqlalchemy.exc import SQLAlchemyError

from app import notify_celery
from app import performance_platform_client, zendesk_client
from app.aws import s3
from app.celery.service_callback_tasks import (
    send_delivery_status_to_service,
    create_encrypted_callback_data,
)
from app.celery.tasks import process_job
from app.config import QueueNames, TaskNames
from app.dao.date_util import get_month_start_and_end_date_in_utc
from app.dao.inbound_sms_dao import delete_inbound_sms_created_more_than_a_week_ago
from app.dao.invited_org_user_dao import delete_org_invitations_created_more_than_two_days_ago
from app.dao.invited_user_dao import delete_invitations_created_more_than_two_days_ago
from app.dao.jobs_dao import (
    dao_get_letter_job_ids_by_status,
    dao_set_scheduled_jobs_to_pending,
    dao_get_jobs_older_than_limited_by
)
from app.dao.jobs_dao import dao_update_job
from app.dao.monthly_billing_dao import (
    get_service_ids_that_need_billing_populated,
    create_or_update_monthly_billing
)
from app.dao.notifications_dao import (
    dao_timeout_notifications,
    is_delivery_slow_for_provider,
    delete_notifications_created_more_than_a_week_ago_by_type,
    dao_get_count_of_letters_to_process_for_date,
    dao_get_scheduled_notifications,
    set_scheduled_notification_to_processed,
    notifications_not_yet_sent
)
from app.dao.provider_details_dao import (
    get_current_provider,
    dao_toggle_sms_provider
)
from app.dao.service_callback_api_dao import get_service_delivery_status_callback_api_for_service
from app.dao.services_dao import (
    dao_fetch_monthly_historical_stats_by_template
)
from app.dao.stats_template_usage_by_month_dao import insert_or_update_stats_for_template
from app.dao.users_dao import delete_codes_older_created_more_than_a_day_ago
from app.exceptions import NotificationTechnicalFailureException
from app.models import (
    Job,
    Notification,
    NOTIFICATION_SENDING,
    LETTER_TYPE,
    JOB_STATUS_IN_PROGRESS,
    JOB_STATUS_READY_TO_SEND,
    JOB_STATUS_ERROR,
    SMS_TYPE,
    EMAIL_TYPE,
    KEY_TYPE_NORMAL
)
from app.notifications.process_notifications import send_notification_to_queue
from app.performance_platform import total_sent_notifications, processing_time
from app.utils import (
    convert_utc_to_bst
)
from app.v2.errors import JobIncompleteError


@notify_celery.task(name="remove_csv_files")
@statsd(namespace="tasks")
def remove_csv_files(job_types):
    jobs = dao_get_jobs_older_than_limited_by(job_types=job_types)
    for job in jobs:
        s3.remove_job_from_s3(job.service_id, job.id)
        current_app.logger.info("Job ID {} has been removed from s3.".format(job.id))


@notify_celery.task(name="run-scheduled-jobs")
@statsd(namespace="tasks")
def run_scheduled_jobs():
    try:
        for job in dao_set_scheduled_jobs_to_pending():
            process_job.apply_async([str(job.id)], queue=QueueNames.JOBS)
            current_app.logger.info("Job ID {} added to process job queue".format(job.id))
    except SQLAlchemyError:
        current_app.logger.exception("Failed to run scheduled jobs")
        raise


@notify_celery.task(name='send-scheduled-notifications')
@statsd(namespace="tasks")
def send_scheduled_notifications():
    try:
        scheduled_notifications = dao_get_scheduled_notifications()
        for notification in scheduled_notifications:
            send_notification_to_queue(notification, notification.service.research_mode)
            set_scheduled_notification_to_processed(notification.id)
        current_app.logger.info(
            "Sent {} scheduled notifications to the provider queue".format(len(scheduled_notifications)))
    except SQLAlchemyError:
        current_app.logger.exception("Failed to send scheduled notifications")
        raise


@notify_celery.task(name="delete-verify-codes")
@statsd(namespace="tasks")
def delete_verify_codes():
    try:
        start = datetime.utcnow()
        deleted = delete_codes_older_created_more_than_a_day_ago()
        current_app.logger.info(
            "Delete job started {} finished {} deleted {} verify codes".format(start, datetime.utcnow(), deleted)
        )
    except SQLAlchemyError:
        current_app.logger.exception("Failed to delete verify codes")
        raise


@notify_celery.task(name="delete-sms-notifications")
@statsd(namespace="tasks")
def delete_sms_notifications_older_than_seven_days():
    try:
        start = datetime.utcnow()
        deleted = delete_notifications_created_more_than_a_week_ago_by_type('sms')
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
@statsd(namespace="tasks")
def delete_email_notifications_older_than_seven_days():
    try:
        start = datetime.utcnow()
        deleted = delete_notifications_created_more_than_a_week_ago_by_type('email')
        current_app.logger.info(
            "Delete {} job started {} finished {} deleted {} email notifications".format(
                'email',
                start,
                datetime.utcnow(),
                deleted
            )
        )
    except SQLAlchemyError:
        current_app.logger.exception("Failed to delete sms notifications")
        raise


@notify_celery.task(name="delete-letter-notifications")
@statsd(namespace="tasks")
def delete_letter_notifications_older_than_seven_days():
    try:
        start = datetime.utcnow()
        deleted = delete_notifications_created_more_than_a_week_ago_by_type('letter')
        current_app.logger.info(
            "Delete {} job started {} finished {} deleted {} letter notifications".format(
                'letter',
                start,
                datetime.utcnow(),
                deleted
            )
        )
    except SQLAlchemyError:
        current_app.logger.exception("Failed to delete sms notifications")
        raise


@notify_celery.task(name="delete-invitations")
@statsd(namespace="tasks")
def delete_invitations():
    try:
        start = datetime.utcnow()
        deleted_invites = delete_invitations_created_more_than_two_days_ago()
        deleted_invites += delete_org_invitations_created_more_than_two_days_ago()
        current_app.logger.info(
            "Delete job started {} finished {} deleted {} invitations".format(start, datetime.utcnow(), deleted_invites)
        )
    except SQLAlchemyError:
        current_app.logger.exception("Failed to delete invitations")
        raise


@notify_celery.task(name='timeout-sending-notifications')
@statsd(namespace="tasks")
def timeout_notifications():
    technical_failure_notifications, temporary_failure_notifications = \
        dao_timeout_notifications(current_app.config.get('SENDING_NOTIFICATIONS_TIMEOUT_PERIOD'))

    notifications = technical_failure_notifications + temporary_failure_notifications
    for notification in notifications:
        # queue callback task only if the service_callback_api exists
        service_callback_api = get_service_delivery_status_callback_api_for_service(service_id=notification.service_id)
        if service_callback_api:
            encrypted_notification = create_encrypted_callback_data(notification, service_callback_api)
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
@statsd(namespace="tasks")
def send_daily_performance_platform_stats():
    if performance_platform_client.active:
        yesterday = datetime.utcnow() - timedelta(days=1)
        send_total_sent_notifications_to_performance_platform(yesterday)
        processing_time.send_processing_time_to_performance_platform()


def send_total_sent_notifications_to_performance_platform(day):
    count_dict = total_sent_notifications.get_total_sent_notifications_for_day(day)
    email_sent_count = count_dict.get('email').get('count')
    sms_sent_count = count_dict.get('sms').get('count')
    letter_sent_count = count_dict.get('letter').get('count')
    start_date = count_dict.get('start_date')

    current_app.logger.info(
        "Attempting to update Performance Platform for {} with {} emails, {} text messages and {} letters"
        .format(start_date, email_sent_count, sms_sent_count, letter_sent_count)
    )

    total_sent_notifications.send_total_notifications_sent_for_day_stats(
        start_date,
        'sms',
        sms_sent_count
    )

    total_sent_notifications.send_total_notifications_sent_for_day_stats(
        start_date,
        'email',
        email_sent_count
    )

    total_sent_notifications.send_total_notifications_sent_for_day_stats(
        start_date,
        'letter',
        letter_sent_count
    )


@notify_celery.task(name='switch-current-sms-provider-on-slow-delivery')
@statsd(namespace="tasks")
def switch_current_sms_provider_on_slow_delivery():
    """
    Switch providers if there are at least two slow delivery notifications (more than four minutes)
    in the last ten minutes. Search from the time we last switched to the current provider.
    """
    functional_test_provider_service_id = current_app.config.get('FUNCTIONAL_TEST_PROVIDER_SERVICE_ID')
    functional_test_provider_template_id = current_app.config.get('FUNCTIONAL_TEST_PROVIDER_SMS_TEMPLATE_ID')

    if functional_test_provider_service_id and functional_test_provider_template_id:
        current_provider = get_current_provider('sms')
        slow_delivery_notifications = is_delivery_slow_for_provider(
            provider=current_provider.identifier,
            threshold=2,
            sent_at=max(datetime.utcnow() - timedelta(minutes=10), current_provider.updated_at),
            delivery_time=timedelta(minutes=4),
            service_id=functional_test_provider_service_id,
            template_id=functional_test_provider_template_id
        )

        if slow_delivery_notifications:
            current_app.logger.warning(
                'Slow delivery notifications detected for provider {}'.format(
                    current_provider.identifier
                )
            )

            dao_toggle_sms_provider(current_provider.identifier)


@notify_celery.task(name="delete-inbound-sms")
@statsd(namespace="tasks")
def delete_inbound_sms_older_than_seven_days():
    try:
        start = datetime.utcnow()
        deleted = delete_inbound_sms_created_more_than_a_week_ago()
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


@notify_celery.task(name="remove_transformed_dvla_files")
@statsd(namespace="tasks")
def remove_transformed_dvla_files():
    jobs = dao_get_jobs_older_than_limited_by(job_types=[LETTER_TYPE])
    for job in jobs:
        s3.remove_transformed_dvla_file(job.id)
        current_app.logger.info("Transformed dvla file for job {} has been removed from s3.".format(job.id))


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
@statsd(namespace="tasks")
def raise_alert_if_letter_notifications_still_sending():

    today = datetime.utcnow().date()

    # Do nothing on the weekend
    if today.isoweekday() in [6, 7]:
        return

    if today.isoweekday() in [1, 2]:
        offset_days = 4
    else:
        offset_days = 2
    still_sending = Notification.query.filter(
        Notification.notification_type == LETTER_TYPE,
        Notification.status == NOTIFICATION_SENDING,
        Notification.key_type == KEY_TYPE_NORMAL,
        func.date(Notification.sent_at) <= today - timedelta(days=offset_days)
    ).count()

    if still_sending:
        message = "There are {} letters in the 'sending' state from {}".format(
            still_sending,
            (today - timedelta(days=offset_days)).strftime('%A %d %B')
        )
        # Only send alerts in production
        if current_app.config['NOTIFY_ENVIRONMENT'] in ['live', 'production', 'test']:
            zendesk_client.create_ticket(
                subject="[{}] Letters still sending".format(current_app.config['NOTIFY_ENVIRONMENT']),
                message=message,
                ticket_type=zendesk_client.TYPE_INCIDENT
            )
        else:
            current_app.logger.info(message)


@notify_celery.task(name="populate_monthly_billing")
@statsd(namespace="tasks")
def populate_monthly_billing():
    # for every service with billable units this month update billing totals for yesterday
    # this will overwrite the existing amount.
    yesterday = datetime.utcnow() - timedelta(days=1)
    yesterday_in_bst = convert_utc_to_bst(yesterday)
    start_date, end_date = get_month_start_and_end_date_in_utc(yesterday_in_bst)
    services = get_service_ids_that_need_billing_populated(start_date=start_date, end_date=end_date)
    [create_or_update_monthly_billing(service_id=s.service_id, billing_month=end_date) for s in services]


@notify_celery.task(name="run-letter-jobs")
@statsd(namespace="tasks")
def run_letter_jobs():
    job_ids = dao_get_letter_job_ids_by_status(JOB_STATUS_READY_TO_SEND)
    if job_ids:
        notify_celery.send_task(
            name=TaskNames.DVLA_JOBS,
            args=(job_ids,),
            queue=QueueNames.PROCESS_FTP
        )
        current_app.logger.info("Queued {} ready letter job ids onto {}".format(len(job_ids), QueueNames.PROCESS_FTP))


@notify_celery.task(name="trigger-letter-pdfs-for-day")
@statsd(namespace="tasks")
def trigger_letter_pdfs_for_day():
    letter_pdfs_count = dao_get_count_of_letters_to_process_for_date()
    if letter_pdfs_count:
        notify_celery.send_task(
            name='collate-letter-pdfs-for-day',
            args=(date.today().strftime("%Y-%m-%d"),),
            queue=QueueNames.LETTERS
        )
    current_app.logger.info("{} letter pdfs to be process by {} task".format(
        letter_pdfs_count, 'collate-letter-pdfs-for-day'))


@notify_celery.task(name='check-job-status')
@statsd(namespace="tasks")
def check_job_status():
    """
    every x minutes do this check
    select
    from jobs
    where job_status == 'in progress'
    and template_type in ('sms', 'email')
    and scheduled_at or created_at is older that 30 minutes.
    if any results then
        raise error
        process the rows in the csv that are missing (in another task) just do the check here.
    """
    thirty_minutes_ago = datetime.utcnow() - timedelta(minutes=30)
    thirty_five_minutes_ago = datetime.utcnow() - timedelta(minutes=35)

    jobs_not_complete_after_30_minutes = Job.query.filter(
        Job.job_status == JOB_STATUS_IN_PROGRESS,
        and_(thirty_five_minutes_ago < Job.processing_started, Job.processing_started < thirty_minutes_ago)
    ).order_by(Job.processing_started).all()

    # temporarily mark them as ERROR so that they don't get picked up by future check_job_status tasks
    # if they haven't been re-processed in time.
    job_ids = []
    for job in jobs_not_complete_after_30_minutes:
        job.job_status = JOB_STATUS_ERROR
        dao_update_job(job)
        job_ids.append(str(job.id))

    if job_ids:
        notify_celery.send_task(
            name=TaskNames.PROCESS_INCOMPLETE_JOBS,
            args=(job_ids,),
            queue=QueueNames.JOBS
        )
        raise JobIncompleteError("Job(s) {} have not completed.".format(job_ids))


@notify_celery.task(name='daily-stats-template-usage-by-month')
@statsd(namespace="tasks")
def daily_stats_template_usage_by_month():
    results = dao_fetch_monthly_historical_stats_by_template()

    for result in results:
        if result.template_id:
            insert_or_update_stats_for_template(
                result.template_id,
                result.month,
                result.year,
                result.count
            )


@notify_celery.task(name='raise-alert-if-no-letter-ack-file')
@statsd(namespace="tasks")
def letter_raise_alert_if_no_ack_file_for_zip():
    # get a list of zip files since yesterday
    zip_file_set = set()

    for key in s3.get_list_of_files_by_suffix(bucket_name=current_app.config['LETTERS_PDF_BUCKET_NAME'],
                                              subfolder=datetime.utcnow().strftime('%Y-%m-%d') + '/zips_sent',
                                              suffix='.TXT'):

        subname = key.split('/')[-1]    # strip subfolder in name
        zip_file_set.add(subname.upper().rstrip('.TXT'))

    # get acknowledgement file
    ack_file_set = set()

    yesterday = datetime.now(tz=pytz.utc) - timedelta(days=1)   # AWS datetime format

    for key in s3.get_list_of_files_by_suffix(bucket_name=current_app.config['DVLA_RESPONSE_BUCKET_NAME'],
                                              subfolder='root/dispatch', suffix='.ACK.txt', last_modified=yesterday):
        ack_file_set.add(key)

    today_str = datetime.utcnow().strftime('%Y%m%d')

    ack_content_set = set()
    for key in ack_file_set:
        if today_str in key:
            content = s3.get_s3_file(current_app.config['DVLA_RESPONSE_BUCKET_NAME'], key)
            for zip_file in content.split('\n'):    # each line
                s = zip_file.split('|')
                ack_content_set.add(s[0].upper())

    message = (
        "Letter ack file does not contain all zip files sent. "
        "Missing ack for zip files: {}, "
        "pdf bucket: {}, subfolder: {}, "
        "ack bucket: {}"
    ).format(
        str(sorted(zip_file_set - ack_content_set)),
        current_app.config['LETTERS_PDF_BUCKET_NAME'],
        datetime.utcnow().strftime('%Y-%m-%d') + '/zips_sent',
        current_app.config['DVLA_RESPONSE_BUCKET_NAME']
    )
    # strip empty element before comparison
    ack_content_set.discard('')
    zip_file_set.discard('')

    if len(zip_file_set - ack_content_set) > 0:
        if current_app.config['NOTIFY_ENVIRONMENT'] in ['live', 'production', 'test']:
            zendesk_client.create_ticket(
                subject="Letter acknowledge error",
                message=message,
                ticket_type=zendesk_client.TYPE_INCIDENT
            )
        current_app.logger.error(message)

    if len(ack_content_set - zip_file_set) > 0:
        current_app.logger.info(
            "letter ack contains zip that is not for today: {}".format(ack_content_set - zip_file_set)
        )


@notify_celery.task(name='replay-created-notifications')
@statsd(namespace="tasks")
def replay_created_notifications():
    # if the notification has not be send after 4 hours + 15 minutes, then try to resend.
    resend_created_notifications_older_than = (60 * 60 * 4) + (60 * 15)
    for notification_type in (EMAIL_TYPE, SMS_TYPE):
        notifications_to_resend = notifications_not_yet_sent(
            resend_created_notifications_older_than,
            notification_type
        )

        current_app.logger.info("Sending {} {} notifications "
                                "to the delivery queue because the notification "
                                "status was created.".format(len(notifications_to_resend), notification_type))

        for n in notifications_to_resend:
            send_notification_to_queue(notification=n, research_mode=n.service.research_mode)
