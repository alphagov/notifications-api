from sqlalchemy.exc import SQLAlchemyError

from app import notify_celery
from flask import current_app
from app.statsd_decorators import statsd
from app.dao.statistics_dao import create_or_update_job_sending_statistics, update_job_stats_outcome_count


@notify_celery.task(bind=True, name='record_initial_job_statistics', max_retries=20, default_retry_delay=300)
@statsd(namespace="tasks")
def record_initial_job_statistics(self, notification):
    try:
        create_or_update_job_sending_statistics(notification)
    except SQLAlchemyError as e:
        current_app.logger.exception(e)
        self.retry(queue="retry")
    except self.MaxRetriesExceededError:
        current_app.logger.error(
            "RETRY FAILED: task record_initial_job_statistics failed for notification {}".format(notification.id)
        )


@notify_celery.task(bind=True, name='record_outcome_job_statistics', max_retries=20, default_retry_delay=300)
@statsd(namespace="tasks")
def record_outcome_job_statistics(self, notification):
    try:
        updated_count = update_job_stats_outcome_count(notification)
        if updated_count == 0:
            self.retry(queue="retry")
    except SQLAlchemyError as e:
        current_app.logger.exception(e)
        self.retry(queue="retry")
    except self.MaxRetriesExceededError:
        current_app.logger.error(
            "RETRY FAILED: task update_job_stats_outcome_count failed for notification {}".format(notification.id)
        )
