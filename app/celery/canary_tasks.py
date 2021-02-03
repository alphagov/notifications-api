from flask import current_app
from notifications_utils.statsd_decorators import statsd

from app import counter, notify_celery


@statsd(namespace="tasks")
def canary_passing_task():
    global counter
    counter += 1

    current_app.logger.info(f'The counter is {counter}.')


@notify_celery.task(name="canary_failing_task", max_retries=60, default_retry_delay=30)
@statsd(namespace="tasks")
def canary_failing_task():
    current_app.logger.info('Calling the failing task')
    raise Exception
