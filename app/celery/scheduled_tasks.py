from datetime import datetime, timedelta

from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

from app.aws import s3
from app import notify_celery
from app.dao.invited_user_dao import delete_invitations_created_more_than_two_days_ago
from app.dao.jobs_dao import dao_get_scheduled_jobs, dao_update_job, dao_get_jobs_older_than
from app.dao.notifications_dao import (delete_notifications_created_more_than_a_week_ago,
                                       dao_timeout_notifications)
from app.dao.users_dao import delete_codes_older_created_more_than_a_day_ago
from app.statsd_decorators import statsd
from app.models import JOB_STATUS_PENDING
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
        jobs = dao_get_scheduled_jobs()
        for job in jobs:
            job.job_status = JOB_STATUS_PENDING
            dao_update_job(job)
            process_job.apply_async([str(job.id)], queue="process-job")
            current_app.logger.info(
                "Job ID {} added to process job queue".format(job.id)
            )
    except SQLAlchemyError as e:
        current_app.logger.exception("Failed to run scheduled jobs", e)
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
        current_app.logger.exception("Failed to delete verify codes", e)
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
        current_app.logger.exception("Failed to delete successful notifications", e)
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
        current_app.logger.exception("Failed to delete failed notifications", e)
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
        current_app.logger.exception("Failed to delete invitations", e)
        raise


@notify_celery.task(name='timeout-sending-notifications')
@statsd(namespace="tasks")
def timeout_notifications():
    try:
        updated = dao_timeout_notifications(current_app.config.get('SENDING_NOTIFICATIONS_TIMEOUT_PERIOD'))
        if updated:
            current_app.logger.info(
                "Timeout period reached for {} notifications, status has been updated.".format(updated))
    except Exception as e:
        current_app.logger.exception(e)
        current_app.logger.error(
            "Exception raised trying to timeout notification skipping notification update."
        )
