from datetime import (
    datetime,
    timedelta
)

from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

from app.aws import s3
from app import notify_celery
from app import performance_platform_client
from app.dao.inbound_sms_dao import delete_inbound_sms_created_more_than_a_week_ago
from app.dao.invited_user_dao import delete_invitations_created_more_than_two_days_ago
from app.dao.jobs_dao import dao_set_scheduled_jobs_to_pending, dao_get_jobs_older_than_limited_by
from app.dao.notifications_dao import (
    dao_timeout_notifications,
    is_delivery_slow_for_provider,
    delete_notifications_created_more_than_a_week_ago_by_type,
    dao_get_scheduled_notifications,
    set_scheduled_notification_to_processed)
from app.dao.statistics_dao import dao_timeout_job_statistics
from app.dao.provider_details_dao import (
    get_current_provider,
    dao_toggle_sms_provider
)
from app.dao.users_dao import delete_codes_older_created_more_than_a_day_ago
from app.notifications.process_notifications import send_notification_to_queue
from app.statsd_decorators import statsd
from app.celery.tasks import process_job
from app.config import QueueNames


@notify_celery.task(name="remove_csv_files")
@statsd(namespace="tasks")
def remove_csv_files():
    jobs = dao_get_jobs_older_than_limited_by()
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
    except SQLAlchemyError as e:
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
    except SQLAlchemyError as e:
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
    except SQLAlchemyError as e:
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
    except SQLAlchemyError as e:
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
    except SQLAlchemyError as e:
        current_app.logger.exception("Failed to delete invitations")
        raise


@notify_celery.task(name='timeout-sending-notifications')
@statsd(namespace="tasks")
def timeout_notifications():
    updated = dao_timeout_notifications(current_app.config.get('SENDING_NOTIFICATIONS_TIMEOUT_PERIOD'))
    if updated:
        current_app.logger.info(
            "Timeout period reached for {} notifications, status has been updated.".format(updated))


@notify_celery.task(name='send-daily-performance-platform-stats')
@statsd(namespace="tasks")
def send_daily_performance_platform_stats():
    if performance_platform_client.active:
        count_dict = performance_platform_client.get_total_sent_notifications_yesterday()
        email_sent_count = count_dict.get('email').get('count')
        sms_sent_count = count_dict.get('sms').get('count')
        start_date = count_dict.get('start_date')

        current_app.logger.info(
            "Attempting to update performance platform for date {} with email count {} and sms count {}"
            .format(start_date, email_sent_count, sms_sent_count)
        )

        performance_platform_client.send_performance_stats(
            start_date,
            'sms',
            sms_sent_count,
            'day'
        )

        performance_platform_client.send_performance_stats(
            start_date,
            'email',
            email_sent_count,
            'day'
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
    except SQLAlchemyError as e:
        current_app.logger.exception("Failed to delete inbound sms notifications")
        raise
