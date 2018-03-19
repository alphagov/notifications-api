import json

from notifications_utils.statsd_decorators import statsd

from app import (
    db,
    DATETIME_FORMAT,
    notify_celery,
    encryption
)
from app.dao.notifications_dao import (
    get_notification_by_id,
)

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
def send_delivery_status_to_service(self, notification_id,
                                    encrypted_status_update=None
                                    ):
    if not encrypted_status_update:
        process_update_with_notification_id(self, notification_id=notification_id)
    else:
        try:
            status_update = encryption.decrypt(encrypted_status_update)

            data = {
                "id": str(notification_id),
                "reference": status_update['notification_client_reference'],
                "to": status_update['notification_to'],
                "status": status_update['notification_status'],
                "created_at": status_update['notification_created_at'],
                "completed_at": status_update['notification_updated_at'],
                "sent_at": status_update['notification_sent_at'],
                "notification_type": status_update['notification_type']
            }

            response = request(
                method="POST",
                url=status_update['service_callback_api_url'],
                data=json.dumps(data),
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer {}'.format(status_update['service_callback_api_bearer_token'])
                },
                timeout=60
            )
            current_app.logger.info('send_delivery_status_to_service sending {} to {}, response {}'.format(
                notification_id,
                status_update['service_callback_api_url'],
                response.status_code
            ))
            response.raise_for_status()
        except RequestException as e:
            current_app.logger.warning(
                "send_delivery_status_to_service request failed for notification_id: {} and url: {}. exc: {}".format(
                    notification_id,
                    status_update['service_callback_api_url'],
                    e
                )
            )
            if not isinstance(e, HTTPError) or e.response.status_code >= 500:
                try:
                    self.retry(queue=QueueNames.RETRY)
                except self.MaxRetriesExceededError:
                    current_app.logger.exception(
                        """Retry: send_delivery_status_to_service has retried the max num of times
                         for notification: {}""".format(notification_id)
                    )


def process_update_with_notification_id(self, notification_id):
    retry = False
    try:
        notification = get_notification_by_id(notification_id)
        service_callback_api = get_service_callback_api_for_service(service_id=notification.service_id)
        if not service_callback_api:
            # No delivery receipt API info set
            return

        # Release DB connection before performing an external HTTP request
        db.session.close()

        data = {
            "id": str(notification_id),
            "reference": str(notification.client_reference),
            "to": notification.to,
            "status": notification.status,
            "created_at": notification.created_at.strftime(DATETIME_FORMAT),
            "completed_at": notification.updated_at.strftime(DATETIME_FORMAT),
            "sent_at": notification.sent_at.strftime(DATETIME_FORMAT),
            "notification_type": notification.notification_type
        }

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
            "send_delivery_status_to_service request failed for notification_id: {} and url: {}. exc: {}".format(
                notification_id,
                service_callback_api.url,
                e
            )
        )
        if not isinstance(e, HTTPError) or e.response.status_code >= 500:
            retry = True
    except Exception as e:
        current_app.logger.exception(
            'Unhandled exception when sending callback for notification {}'.format(notification_id)
        )
        retry = True

    if retry:
        try:
            self.retry(queue=QueueNames.RETRY)
        except self.MaxRetriesExceededError:
            current_app.logger.exception(
                """Retry: send_delivery_status_to_service has retried the max num of times
                 for notification: {}""".format(notification_id)
            )


def create_encrypted_callback_data(notification, service_callback_api):
    from app import DATETIME_FORMAT, encryption
    data = {
        "notification_id": str(notification.id),
        "notification_client_reference": notification.client_reference,
        "notification_to": notification.to,
        "notification_status": notification.status,
        "notification_created_at": notification.created_at.strftime(DATETIME_FORMAT),
        "notification_updated_at":
            notification.updated_at.strftime(DATETIME_FORMAT) if notification.updated_at else None,
        "notification_sent_at": notification.sent_at.strftime(DATETIME_FORMAT) if notification.sent_at else None,
        "notification_type": notification.notification_type,
        "service_callback_api_url": service_callback_api.url,
        "service_callback_api_bearer_token": service_callback_api.bearer_token,
    }
    return encryption.encrypt(data)
