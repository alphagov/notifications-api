from datetime import datetime, timedelta

from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

from app.aws import s3
from app import notify_celery
from app.dao.invited_user_dao import delete_invitations_created_more_than_two_days_ago
from app.dao.jobs_dao import dao_set_scheduled_jobs_to_pending, dao_get_jobs_older_than
from app.dao.notifications_dao import (dao_provider_notifications_where_delivery_longer_than,
                                       delete_notifications_created_more_than_a_week_ago,
                                       dao_timeout_notifications)
from app.dao.provider_details_dao import dao_switch_sms_provider
from app.dao.users_dao import delete_codes_older_created_more_than_a_day_ago
from app.statsd_decorators import statsd
from app.celery.tasks import process_job


@notify_celery.task(name="remove_csv_files")
@statsd(namespace="tasks")
def remove_csv_files():
    jobs = dao_get_jobs_older_than(7)
    for job in jobs:
        s3.remove_job_from_s3(job.service_id, job.id)
        current_app.logger.info("Job ID {} has been removed from s3.".format(job.id))


@notify_celery.task(name="run-scheduled-jobs")
@statsd(namespace="tasks")
def run_scheduled_jobs():
    try:
        for job in dao_set_scheduled_jobs_to_pending():
            process_job.apply_async([str(job.id)], queue="process-job")
            current_app.logger.info("Job ID {} added to process job queue".format(job.id))
    except SQLAlchemyError as e:
        current_app.logger.exception("Failed to run scheduled jobs")
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


@notify_celery.task(name="delete-successful-notifications")
@statsd(namespace="tasks")
def delete_successful_notifications():
    try:
        start = datetime.utcnow()
        deleted = delete_notifications_created_more_than_a_week_ago('delivered')
        current_app.logger.info(
            "Delete job started {} finished {} deleted {} successful notifications".format(
                start,
                datetime.utcnow(),
                deleted
            )
        )
    except SQLAlchemyError as e:
        current_app.logger.exception("Failed to delete successful notifications")
        raise


@notify_celery.task(name="delete-failed-notifications")
@statsd(namespace="tasks")
def delete_failed_notifications():
    try:
        start = datetime.utcnow()
        deleted = delete_notifications_created_more_than_a_week_ago('failed')
        deleted += delete_notifications_created_more_than_a_week_ago('technical-failure')
        deleted += delete_notifications_created_more_than_a_week_ago('temporary-failure')
        deleted += delete_notifications_created_more_than_a_week_ago('permanent-failure')
        current_app.logger.info(
            "Delete job started {} finished {} deleted {} failed notifications".format(
                start,
                datetime.utcnow(),
                deleted
            )
        )
    except SQLAlchemyError as e:
        current_app.logger.exception("Failed to delete failed notifications")
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


@notify_celery.task(name='switch-sms-providers-on-slow-delivery')
@statsd(namespace="tasks")
def switch_providers_on_slow_delivery():
    # According to functional provider tests, any notification that
    # took longer than 4 minutes to deliver is a failure
    last_ten_minutes = datetime.utcnow() - timedelta(minutes=10)
    four_minutes = timedelta(minutes=4)

    slow_delivery_notifications = dao_provider_notifications_where_delivery_longer_than(
        amount_of_time=four_minutes,
        starting_from=last_ten_minutes,
        service_id=current_app.config.get('FUNCTIONAL_TEST_SERVICE_ID'),
        template_id=current_app.config.get('FUNCTIONAL_TEST_TEMPLATE_ID'),
        providers=['firetext', 'mmg']  # Only want to switch between these two for now
    )

    if slow_delivery_notifications:
        notification = slow_delivery_notifications[0]
        current_app.logger.warning(
            'Slow delivery notification found with id: {} created at: {} sent at: {} by: {}'.format(
                notification.id,
                notification.created_at,
                notification.sent_at,
                notification.sent_by
            )
        )
        dao_switch_sms_provider(notification.sent_by)
    else:
        current_app.logger.info('No slow delivery notifications')
