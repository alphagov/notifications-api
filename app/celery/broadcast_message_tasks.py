import uuid

from flask import current_app
from notifications_utils.statsd_decorators import statsd
from sqlalchemy.schema import Sequence

from app import cbc_proxy_client, db, notify_celery
from app.config import QueueNames
from app.models import BroadcastEventMessageType, BroadcastProvider
from app.dao.broadcast_message_dao import dao_get_broadcast_event_by_id, create_broadcast_provider_message

from app.utils import format_sequential_number


@notify_celery.task(name="send-broadcast-event")
@statsd(namespace="tasks")
def send_broadcast_event(broadcast_event_id):
    if not current_app.config['CBC_PROXY_ENABLED']:
        current_app.logger.info(f'CBC Proxy disabled, not sending broadcast_event {broadcast_event_id}')
        return

    broadcast_event = dao_get_broadcast_event_by_id(broadcast_event_id)
    for provider in broadcast_event.service.get_available_broadcast_providers():
        send_broadcast_provider_message.apply_async(
            kwargs={'broadcast_event_id': broadcast_event_id, 'provider': provider},
            queue=QueueNames.NOTIFY
        )


@notify_celery.task(name="send-broadcast-provider-message")
@statsd(namespace="tasks")
def send_broadcast_provider_message(broadcast_event_id, provider):
    broadcast_event = dao_get_broadcast_event_by_id(broadcast_event_id)

    broadcast_provider_message = create_broadcast_provider_message(broadcast_event, provider)

    current_app.logger.info(
        f'invoking cbc proxy to send '
        f'broadcast_event {broadcast_event.reference} '
        f'msgType {broadcast_event.message_type}'
    )

    areas = [
        {"polygon": polygon}
        for polygon in broadcast_event.transmitted_areas["simple_polygons"]
    ]

    cbc_proxy_provider_client = cbc_proxy_client.get_proxy(provider)

    if broadcast_event.message_type == BroadcastEventMessageType.ALERT:
        cbc_proxy_provider_client.create_and_send_broadcast(
            identifier=str(broadcast_provider_message.id),
            headline="GOV.UK Notify Broadcast",
            description=broadcast_event.transmitted_content['body'],
            areas=areas,
            sent=broadcast_event.sent_at_as_cap_datetime_string,
            expires=broadcast_event.transmitted_finishes_at_as_cap_datetime_string,
        )
    elif broadcast_event.message_type == BroadcastEventMessageType.UPDATE:
        cbc_proxy_provider_client.update_and_send_broadcast(
            identifier=str(broadcast_provider_message.id),
            headline="GOV.UK Notify Broadcast",
            description=broadcast_event.transmitted_content['body'],
            areas=areas,
            previous_provider_messages=broadcast_event.get_earlier_provider_messages(provider),
            sent=broadcast_event.sent_at_as_cap_datetime_string,
            expires=broadcast_event.transmitted_finishes_at_as_cap_datetime_string,
        )
    elif broadcast_event.message_type == BroadcastEventMessageType.CANCEL:
        cbc_proxy_provider_client.cancel_broadcast(
            identifier=str(broadcast_provider_message.id),
            headline="GOV.UK Notify Broadcast",
            description=broadcast_event.transmitted_content['body'],
            areas=areas,
            previous_provider_messages=broadcast_event.get_earlier_provider_messages(provider),
            sent=broadcast_event.sent_at_as_cap_datetime_string,
            expires=broadcast_event.transmitted_finishes_at_as_cap_datetime_string,
        )


@notify_celery.task(name='trigger-link-test')
def trigger_link_test(provider):
    identifier = str(uuid.uuid4())
    formatted_seq_number = None
    if provider == BroadcastProvider.VODAFONE:
        sequence = Sequence('broadcast_provider_message_number_seq')
        sequential_number = db.session.connection().execute(sequence)
        formatted_seq_number = format_sequential_number(sequential_number)
    message = f"Sending a link test to CBC proxy for provider {provider} with ID {identifier}"
    current_app.logger.info(message)
    cbc_proxy_client.get_proxy(provider).send_link_test(identifier, formatted_seq_number)
