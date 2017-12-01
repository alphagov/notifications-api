import json
from app import (
    DATETIME_FORMAT,
    notify_celery,
)
from app.dao.notifications_dao import (
    get_notification_by_id,
)

from app.statsd_decorators import statsd
from app.dao.service_callback_api_dao import get_service_callback_api_for_service
from requests import (
    HTTPError,
    request,
    RequestException
)
from flask import current_app
from app.config import QueueNames


@notify_celery.task(bind=True, name="send-delivery-status", max_retries=5, default_retry_delay=300)
@statsd(namespace="tasks")
def send_delivery_status_to_service(self, notification_id):
    # TODO: do we need to do rate limit this?
    notification = get_notification_by_id(notification_id)
    service_callback_api = get_service_callback_api_for_service(service_id=notification.service_id)
    if not service_callback_api:
        # No delivery receipt API info set
        return

    data = {
        "id": str(notification_id),
        "reference": str(notification.client_reference),
        "to": notification.to,
        "status": notification.status,
        "created_at": notification.created_at.strftime(DATETIME_FORMAT),     # the time GOV.UK email sent the request
        "updated_at": notification.updated_at.strftime(DATETIME_FORMAT),     # the last time the status was updated
        "sent_at": notification.sent_at.strftime(DATETIME_FORMAT),           # the time the email was sent
        "notification_type": notification.notification_type
    }

    try:
        response = request(
            method="POST",
            url=service_callback_api.url,
            data=json.dumps(data),
            headers={
                'Content-Type': 'application/json',
                'Authorization': 'Bearer {}'.format(service_callback_api.bearer_token)
            },
            timeout=60
        )
        current_app.logger.info('send_delivery_status_to_service sending {} to {}, response {}'.format(
            notification_id,
            service_callback_api.url,
            response.status_code
        ))
        response.raise_for_status()
    except RequestException as e:
        current_app.logger.warning(
            "send_inbound_sms_to_service request failed for service_id: {} and url: {}. exc: {}".format(
                notification_id,
                service_callback_api.url,
                e
            )
        )
        if not isinstance(e, HTTPError) or e.response.status_code >= 500:
            try:
                self.retry(queue=QueueNames.RETRY)
            except self.MaxRetriesExceededError:
                current_app.logger.exception('Retry: send_inbound_sms_to_service has retried the max number of times')
