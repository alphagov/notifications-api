import logging
import uuid
from datetime import datetime

from flask import current_app
from notifications_utils.clients.otel.utils import default_histogram_bucket
from notifications_utils.template import SMSMessageTemplate
from opentelemetry import metrics

from app import notify_celery, statsd_client
from app.clients import ClientException
from app.clients.sms.firetext import get_firetext_responses
from app.clients.sms.mmg import get_mmg_responses
from app.constants import NOTIFICATION_PENDING
from app.dao import notifications_dao
from app.dao.templates_dao import dao_get_template_by_id
from app.notifications.notifications_ses_callback import (
    check_and_queue_callback_task,
)

sms_response_mapper = {
    "MMG": get_mmg_responses,
    "Firetext": get_firetext_responses,
}

meter = metrics.get_meter(__name__)

otel_provider_callback_completed = meter.create_histogram(
    "provider_sms",
    description="Time for sms sends to complete in seconds",
    explicit_bucket_boundaries_advisory=default_histogram_bucket,
    unit="seconds",
)

otel_sms_international = meter.create_counter(
    "international_sms",
    description="Count of provider callbacks",
)


@notify_celery.task(
    bind=True, name="process-sms-client-response", max_retries=5, default_retry_delay=300, early_log_level=logging.DEBUG
)
def process_sms_client_response(self, status, provider_reference, client_name, detailed_status_code=None):
    # validate reference
    try:
        uuid.UUID(provider_reference, version=4)
    except ValueError as e:
        current_app.logger.exception("%s callback with invalid reference %s", client_name, provider_reference)
        raise e

    response_parser = sms_response_mapper[client_name]

    # validate status
    try:
        notification_status, detailed_status = response_parser(status, detailed_status_code)
        current_app.logger.info(
            "%s callback returned status of %s(%s): %s(%s) for reference: %s",
            client_name,
            notification_status,
            status,
            detailed_status,
            detailed_status_code,
            provider_reference,
        )
    except KeyError as e:
        _process_for_status(
            notification_status="technical-failure", client_name=client_name, provider_reference=provider_reference
        )
        raise ClientException(f"{client_name} callback failed: status {status} not found.") from e

    _process_for_status(
        notification_status=notification_status,
        client_name=client_name,
        provider_reference=provider_reference,
        detailed_status_code=detailed_status_code,
    )


def _process_for_status(notification_status, client_name, provider_reference, detailed_status_code=None):
    # record stats
    notification = notifications_dao.update_notification_status_by_id(
        notification_id=provider_reference,
        status=notification_status,
        sent_by=client_name.lower(),
        detailed_status_code=detailed_status_code,
    )
    if not notification:
        return

    statsd_client.incr(f"callback.{client_name.lower()}.{notification_status}")

    if notification.sent_at:
        statsd_client.timing_with_dates(
            f"callback.{client_name.lower()}.{notification_status}.elapsed-time",
            datetime.utcnow(),
            notification.sent_at,
        )

        otel_provider_callback_completed.record(
            (datetime.utcnow() - notification.sent_at).total_seconds(),
            {
                "client_name": client_name.lower(),
                "notification_status": notification_status,
            },
        )

    if notification.billable_units == 0:
        service = notification.service
        template_model = dao_get_template_by_id(notification.template_id, notification.template_version)

        template = SMSMessageTemplate(
            template_model.__dict__,
            values=notification.personalisation,
            prefix=service.name,
            show_prefix=service.prefix_sms,
        )
        notification.billable_units = template.fragment_count
        notifications_dao.dao_update_notification(notification)

    if notification_status != NOTIFICATION_PENDING:
        check_and_queue_callback_task(notification)
        if notification.international:
            statsd_client.incr(f"international-sms.{notification_status}.{notification.phone_prefix}")
            otel_sms_international.add(
                1,
                {
                    "notification_status": notification_status,
                    "phone_prefix": notification.phone_prefix,
                },
            )
