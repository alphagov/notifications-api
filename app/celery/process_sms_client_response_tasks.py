import logging
import uuid
from datetime import datetime

from flask import current_app
from notifications_utils.template import SMSMessageTemplate
from sqlalchemy.exc import OperationalError

from app import notify_celery, statsd_client
from app.celery import notification_deliver_duration_histogram
from app.clients import ClientException
from app.clients.sms.firetext import get_firetext_responses
from app.clients.sms.mmg import get_mmg_responses
from app.config import QueueNames
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


@notify_celery.task(
    bind=True, name="process-sms-client-response", max_retries=5, default_retry_delay=300, early_log_level=logging.DEBUG
)
def process_sms_client_response(
    self,
    status,
    provider_reference,
    client_name,
    detailed_status_code=None,
    delivery_iso_timestamp: str | None = None,
    receipt_iso_timestamp: str | None = None,
):
    # validate reference
    try:
        uuid.UUID(provider_reference, version=4)
    except ValueError as e:
        extra = {
            "client_name": client_name,
            # for sms, we happen to use notification id as the "provider reference"
            "notification_id": provider_reference,
        }
        current_app.logger.exception(
            "%(client_name)s callback with invalid reference %(notification_id)s",
            extra,
            extra=extra,
        )
        raise e

    response_parser = sms_response_mapper[client_name]

    # validate status
    try:
        try:
            notification_status, detailed_status = response_parser(status, detailed_status_code)

            delivery_dt = None
            if delivery_iso_timestamp is not None:
                try:
                    delivery_dt = datetime.fromisoformat(delivery_iso_timestamp)
                except ValueError:
                    pass  # None it is, then

            receipt_dt = None
            if receipt_iso_timestamp is not None:
                try:
                    receipt_dt = datetime.fromisoformat(receipt_iso_timestamp)
                except ValueError:
                    pass  # None it is, then

            uniform_now = datetime.utcnow()
            extra = {
                "client_name": client_name,
                "notification_status": notification_status,
                "provider_status": status,
                "detailed_status": detailed_status,
                "detailed_status_code": detailed_status_code,
                "receipt_received_at": receipt_dt,
                "receipt_received_ago": (uniform_now - receipt_dt).total_seconds() if receipt_dt is not None else None,
                "delivered_at": delivery_dt,
                "delivered_ago": (uniform_now - delivery_dt).total_seconds() if delivery_dt is not None else None,
                # for sms, we happen to use notification id as the "provider reference"
                "notification_id": provider_reference,
            }
            current_app.logger.info(
                "%(client_name)s callback returned status of %(notification_status)s(%(provider_status)s): "
                "%(detailed_status)s(%(detailed_status_code)s) for reference: %(notification_id)s",
                extra,
                extra=extra,
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
    except OperationalError:
        self.retry(queue=QueueNames.RETRY)


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

    # n.b. notification.sent_at should never be None here
    if notification.sent_at:
        statsd_client.timing_with_dates(
            f"callback.{client_name.lower()}.{notification_status}.elapsed-time",
            datetime.utcnow(),
            notification.sent_at,
        )

        notification_deliver_duration_histogram.record(
            (datetime.utcnow() - notification.sent_at).total_seconds(),
            {
                "key.type": notification.key_type,
                "notification.status": notification_status,
                "notification.type": "sms",
                "notification.sms.country_code": notification.phone_prefix,
                "notification.sms.international": notification.international,
                "provider.name": client_name.lower(),
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
