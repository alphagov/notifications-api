import uuid
from datetime import datetime

from flask import current_app
from notifications_utils.statsd_decorators import statsd
from notifications_utils.template import SMSMessageTemplate

from app import notify_celery, statsd_client
from app.clients import ClientException
from app.clients.sms.firetext import get_firetext_responses
from app.clients.sms.mmg import get_mmg_responses
from app.celery.service_callback_tasks import send_delivery_status_to_service, create_delivery_status_callback_data
from app.config import QueueNames
from app.dao import notifications_dao
from app.dao.service_callback_api_dao import get_service_delivery_status_callback_api_for_service
from app.dao.templates_dao import dao_get_template_by_id
from app.models import NOTIFICATION_PENDING

sms_response_mapper = {
    'MMG': get_mmg_responses,
    'Firetext': get_firetext_responses
}


@notify_celery.task(bind=True, name="process-sms-client-response", max_retries=5, default_retry_delay=300)
@statsd(namespace="tasks")
def process_sms_client_response(self, status, provider_reference, client_name, code=None):
    # validate reference
    try:
        uuid.UUID(provider_reference, version=4)
    except ValueError as e:
        current_app.logger.exception(f'{client_name} callback with invalid reference {provider_reference}')
        raise e

    response_parser = sms_response_mapper[client_name]

    # validate status
    try:
        notification_status, detailed_status = response_parser(status, code)
        current_app.logger.info(
            f'{client_name} callback returned '
            f'status of {notification_status}: {detailed_status} for reference: {provider_reference}'
        )
    except KeyError:
        _process_for_status(
            notification_status='technical-failure',
            client_name=client_name,
            provider_reference=provider_reference
        )
        raise ClientException(f'{client_name} callback failed: status {status} not found.')

    _process_for_status(
        notification_status=notification_status,
        client_name=client_name,
        provider_reference=provider_reference,
        code=code
    )


def _process_for_status(notification_status, client_name, provider_reference, code=None):
    # record stats
    notification = notifications_dao.update_notification_status_by_id(
        notification_id=provider_reference,
        status=notification_status,
        sent_by=client_name.lower(),
        code=code
    )
    if not notification:
        return

    statsd_client.incr('callback.{}.{}'.format(client_name.lower(), notification_status))

    if notification.sent_at:
        statsd_client.timing_with_dates(
            'callback.{}.elapsed-time'.format(client_name.lower()),
            datetime.utcnow(),
            notification.sent_at
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
        service_callback_api = get_service_delivery_status_callback_api_for_service(service_id=notification.service_id)
        # queue callback task only if the service_callback_api exists
        if service_callback_api:
            encrypted_notification = create_delivery_status_callback_data(notification, service_callback_api)
            send_delivery_status_to_service.apply_async([str(notification.id), encrypted_notification],
                                                        queue=QueueNames.CALLBACKS)
