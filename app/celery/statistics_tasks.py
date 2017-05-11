from sqlalchemy.exc import SQLAlchemyError

from app import notify_celery
from flask import current_app

from app.models import JobStatistics
from app.statsd_decorators import statsd
from app.dao.statistics_dao import (
    create_or_update_job_sending_statistics,
    update_job_stats_outcome_count
)
from app.dao.notifications_dao import get_notification_by_id
from app.models import NOTIFICATION_STATUS_TYPES_COMPLETED


def create_initial_notification_statistic_tasks(notification):
    if notification.job_id and notification.status not in NOTIFICATION_STATUS_TYPES_COMPLETED:
        record_initial_job_statistics.apply_async((str(notification.id),), queue="statistics")


def create_outcome_notification_statistic_tasks(notification):
    if notification.job_id and notification.status in NOTIFICATION_STATUS_TYPES_COMPLETED:
        record_outcome_job_statistics.apply_async((str(notification.id),), queue="statistics")


@notify_celery.task(bind=True, name='record_initial_job_statistics', max_retries=20, default_retry_delay=10)
@statsd(namespace="tasks")
def record_initial_job_statistics(self, notification_id):
    notification = None
    try:
        notification = get_notification_by_id(notification_id)
        if notification:
            create_or_update_job_sending_statistics(notification)
        else:
            raise SQLAlchemyError("Failed to find notification with id {}".format(notification_id))
    except SQLAlchemyError as e:
        current_app.logger.exception(e)
        self.retry(queue="retry")
    except self.MaxRetriesExceededError:
        current_app.logger.error(
            "RETRY FAILED: task record_initial_job_statistics failed for notification {}".format(
                notification.id if notification else "missing ID"
            )
        )


@notify_celery.task(bind=True, name='record_outcome_job_statistics', max_retries=20, default_retry_delay=10)
@statsd(namespace="tasks")
def record_outcome_job_statistics(self, notification_id):
    notification = None
    try:
        notification = get_notification_by_id(notification_id)
        if notification:
            updated_count = update_job_stats_outcome_count(notification)
            if updated_count == 0:
                self.retry(queue="retry")
        else:
            raise SQLAlchemyError("Failed to find notification with id {}".format(notification_id))
    except SQLAlchemyError as e:
        current_app.logger.exception(e)
        self.retry(queue="retry")
    except self.MaxRetriesExceededError:
        current_app.logger.error(
            "RETRY FAILED: task update_job_stats_outcome_count failed for notification {}".format(
                notification.id if notification else "missing ID"
            )
        )
