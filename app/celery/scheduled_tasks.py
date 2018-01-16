from datetime import (
    date,
    datetime,
    timedelta
)

from celery.signals import worker_process_shutdown
from flask import current_app
from sqlalchemy import and_
from sqlalchemy.exc import SQLAlchemyError
from notifications_utils.s3 import s3upload

from app.aws import s3
from app import notify_celery
from app.dao.services_dao import (
    dao_fetch_monthly_historical_stats_by_template
)
from app.dao.stats_template_usage_by_month_dao import insert_or_update_stats_for_template
from app.performance_platform import total_sent_notifications, processing_time
from app import performance_platform_client
from app.dao.date_util import get_month_start_and_end_date_in_utc
from app.dao.inbound_sms_dao import delete_inbound_sms_created_more_than_a_week_ago
from app.dao.invited_user_dao import delete_invitations_created_more_than_two_days_ago
from app.dao.jobs_dao import (
    dao_get_letter_job_ids_by_status,
    dao_set_scheduled_jobs_to_pending,
    dao_get_jobs_older_than_limited_by
)
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
    dao_set_created_live_letter_api_notifications_to_pending,
)
from app.dao.statistics_dao import dao_timeout_job_statistics
from app.dao.provider_details_dao import (
    get_current_provider,
    dao_toggle_sms_provider
)
from app.dao.users_dao import delete_codes_older_created_more_than_a_day_ago
from app.models import (
    Job,
    LETTER_TYPE,
    JOB_STATUS_IN_PROGRESS,
    JOB_STATUS_READY_TO_SEND
)
from app.notifications.process_notifications import send_notification_to_queue
from app.statsd_decorators import statsd
from app.celery.tasks import (
    create_dvla_file_contents_for_notifications,
    process_job
)
from app.config import QueueNames, TaskNames
from app.utils import convert_utc_to_bst
from app.v2.errors import JobIncompleteError, NoAckFileReceived
from app.dao.service_callback_api_dao import get_service_callback_api_for_service
from app.celery.service_callback_tasks import send_delivery_status_to_service


@worker_process_shutdown.connect
def worker_process_shutdown(sender, signal, pid, exitcode):
    current_app.logger.info('Scheduled tasks worker shutdown: PID: {} Exitcode: {}'.format(pid, exitcode))


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
        deleted = delete_invitations_created_more_than_two_days_ago()
        current_app.logger.info(
            "Delete job started {} finished {} deleted {} invitations".format(start, datetime.utcnow(), deleted)
        )
    except SQLAlchemyError:
        current_app.logger.exception("Failed to delete invitations")
        raise


@notify_celery.task(name='timeout-sending-notifications')
@statsd(namespace="tasks")
def timeout_notifications():
    notifications = dao_timeout_notifications(current_app.config.get('SENDING_NOTIFICATIONS_TIMEOUT_PERIOD'))

    if notifications:
        for notification in notifications:
            # queue callback task only if the service_callback_api exists
            service_callback_api = get_service_callback_api_for_service(service_id=notification.service_id)

            if service_callback_api:
                send_delivery_status_to_service.apply_async([str(id)], queue=QueueNames.CALLBACKS)

        current_app.logger.info(
            "Timeout period reached for {} notifications, status has been updated.".format(len(notifications)))


@notify_celery.task(name='send-daily-performance-platform-stats')
@statsd(namespace="tasks")
def send_daily_performance_platform_stats():
    if performance_platform_client.active:
        send_total_sent_notifications_to_performance_platform()
        processing_time.send_processing_time_to_performance_platform()


def send_total_sent_notifications_to_performance_platform():
    count_dict = total_sent_notifications.get_total_sent_notifications_yesterday()
    email_sent_count = count_dict.get('email').get('count')
    sms_sent_count = count_dict.get('sms').get('count')
    start_date = count_dict.get('start_date')

    current_app.logger.info(
        "Attempting to update performance platform for date {} with email count {} and sms count {}"
        .format(start_date, email_sent_count, sms_sent_count)
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


@notify_celery.task(name='timeout-job-statistics')
@statsd(namespace="tasks")
def timeout_job_statistics():
    updated = dao_timeout_job_statistics(current_app.config.get('SENDING_NOTIFICATIONS_TIMEOUT_PERIOD'))
    if updated:
        current_app.logger.info(
            "Timeout period reached for {} job statistics, failure count has been updated.".format(updated))


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


@notify_celery.task(name="run-letter-api-notifications")
@statsd(namespace="tasks")
def run_letter_api_notifications():
    current_time = datetime.utcnow().isoformat()

    notifications = dao_set_created_live_letter_api_notifications_to_pending()

    if notifications:
        file_contents = create_dvla_file_contents_for_notifications(notifications)

        filename = '{}-dvla-notifications.txt'.format(current_time)
        s3upload(
            filedata=file_contents + '\n',
            region=current_app.config['AWS_REGION'],
            bucket_name=current_app.config['DVLA_BUCKETS']['notification'],
            file_location=filename
        )

        notify_celery.send_task(
            name=TaskNames.DVLA_NOTIFICATIONS,
            kwargs={'filename': filename},
            queue=QueueNames.PROCESS_FTP
        )
        current_app.logger.info(
            "Queued {} ready letter api notifications onto {}".format(
                len(notifications),
                QueueNames.PROCESS_FTP
            )
        )


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

    job_ids = [str(x.id) for x in jobs_not_complete_after_30_minutes]
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
    zip_file_list = []

    for key in s3.get_list_of_files_by_suffix(bucket_name=current_app.config['LETTERS_PDF_BUCKET_NAME'],
                                              subfolder=datetime.utcnow().strftime('%Y-%m-%d'),
                                              suffix='.zip'):
        zip_file_list.append(key)

    # get acknowledgement file
    ack_file_list = []
    # yesterday = datetime.now(tz=pytz.utc) - timedelta(days=1)
    yesterday = datetime.utcnow() - timedelta(days=1)
    for key in s3.get_list_of_files_by_suffix(bucket_name=current_app.config['DVLA_RESPONSE_BUCKET_NAME'],
                                              subfolder='root/dispatch', suffix='.ACK.txt', lastModified=yesterday):
        ack_file_list.append(key)

    today_str = datetime.utcnow().strftime('%Y%m%d')
    zip_not_today = []

    for key in ack_file_list:
        if today_str in key:
            content = s3.get_s3_file(current_app.config['DVLA_RESPONSE_BUCKET_NAME'], key)
            for zip_file in content.split('\n'):    # each line
                s = zip_file.split('|')
                for zf in zip_file_list:
                    if s[0].lower() in zf.lower():
                        zip_file_list.remove(zf)
                    else:
                        zip_not_today.append(s[0])

    if zip_file_list:

        raise NoAckFileReceived(message=zip_file_list)

    if zip_not_today:
        current_app.logger.info(
            "letter ack contains zip that is not for today {} ".format(zip_not_today)
        )
