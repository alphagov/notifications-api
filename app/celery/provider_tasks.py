import json

from datetime import datetime
from monotonic import monotonic
from flask import current_app
from app import notify_celery, statsd_client, encryption, clients
from app.clients.sms import SmsClientException
from app.dao.notifications_dao import (
    update_provider_stats,
    get_notification_by_id,
    dao_update_notification, update_notification_status_by_id)
from app.dao.provider_details_dao import get_provider_details_by_notification_type
from app.dao.services_dao import dao_fetch_service_by_id
from app.celery.research_mode_tasks import send_sms_response

from notifications_utils.recipients import (
    validate_and_format_phone_number
)

from app.dao.templates_dao import dao_get_template_by_id
from notifications_utils.template import (
    Template,
    unlink_govuk_escaped
)


def retry_iteration_to_delay(retry=0):
    """
    Given current retry calculate some delay before retrying
    0: 10 seconds
    1: 60 seconds (1 minutes)
    2: 300 seconds (5 minutes)
    3: 3600 seconds (60 minutes)
    4: 14400 seconds (4 hours)
    :param retry (zero indexed):
    :return length to retry in seconds, default 10 seconds
    """

    delays = {
        0: 10,
        1: 60,
        2: 300,
        3: 3600,
        4: 14400
    }

    return delays.get(retry, 10)


@notify_celery.task(bind=True, name="send-sms-to-provider", max_retries=5, default_retry_delay=5)
def send_sms_to_provider(self, service_id, notification_id, encrypted_notification=None):
    task_start = monotonic()

    service = dao_fetch_service_by_id(service_id)
    provider = provider_to_use('sms', notification_id)
    notification = get_notification_by_id(notification_id)

    # notification_json = encryption.decrypt(encrypted_notification)

    template = Template(
        dao_get_template_by_id(notification.template_id, notification.template_version).__dict__,
        values=notification.personalisation['personalisation'] if notification.personalisation[
            'personalisation'] else {},
        prefix=service.name
    )
    try:
        if service.research_mode:
            send_sms_response.apply_async(
                (provider.get_name(), str(notification_id), notification.to), queue='research-mode'
            )
        else:
            provider.send_sms(
                to=validate_and_format_phone_number(notification.to),
                content=template.replaced,
                reference=str(notification_id)
            )

            update_provider_stats(
                notification_id,
                'sms',
                provider.get_name(),
                content_char_count=template.replaced_content_count
            )

        notification.sent_at = datetime.utcnow()
        notification.sent_by = provider.get_name(),
        notification.content_char_count = template.replaced_content_count
        notification.status = 'sending'
        dao_update_notification(notification)
    except SmsClientException as e:
        try:
            current_app.logger.error(
                "SMS notification {} failed".format(notification_id)
            )
            current_app.logger.exception(e)
            self.retry(queue="retry", countdown=retry_iteration_to_delay(self.request.retries))
        except self.MaxRetriesExceededError:
            update_notification_status_by_id(notification.id, 'technical-failure', 'failure')

    current_app.logger.info(
        "SMS {} created at {} sent at {}".format(notification_id, notification.created_at, notification.sent_at)
    )
    statsd_client.incr("notifications.tasks.send-sms-to-provider")
    statsd_client.timing("notifications.tasks.send-sms-to-provider.task-time", monotonic() - task_start)
    statsd_client.timing("notifications.sms.total-time", datetime.utcnow() - notification.created_at)


def provider_to_use(notification_type, notification_id):
    active_providers_in_order = [
        provider for provider in get_provider_details_by_notification_type(notification_type) if provider.active
        ]

    if not active_providers_in_order:
        current_app.logger.error(
            "{} {} failed as no active providers".format(notification_type, notification_id)
        )
        raise Exception("No active {} providers".format(notification_type))

    return clients.get_client_by_name_and_type(active_providers_in_order[0].identifier, notification_type)
