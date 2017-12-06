from flask import current_app

from app import notify_celery
from app.config import QueueNames
from app.statsd_decorators import statsd
from app.notifications.notifications_ses_callback import process_ses_response


@notify_celery.task(bind=True, name="process-ses-result", max_retries=5, default_retry_delay=300)
@statsd(namespace="tasks")
def process_ses_results(self, response):
    try:
        errors = process_ses_response(response)
        if errors:
            current_app.logger.error(errors)
    except Exception as exc:
        current_app.logger.exception('Error processing SES results')
        self.retry(queue=QueueNames.RETRY)
