import uuid
from datetime import datetime

from flask import current_app
from notifications_utils.statsd_decorators import statsd
from sqlalchemy.schema import Sequence
from celery.exceptions import MaxRetriesExceededError

from app import cbc_proxy_client, db, notify_celery
from app.clients.cbc_proxy import CBCProxyFatalException, CBCProxyRetryableException
from app.config import QueueNames
from app.models import BroadcastEventMessageType, BroadcastProvider
from app.dao.broadcast_message_dao import dao_get_broadcast_event_by_id, create_broadcast_provider_message

from app.utils import format_sequential_number


def get_retry_delay(retry_count):
    """
    Given a count of retries so far, return a delay for the next one.
    `retry_count` should be 0 the first time a task fails.
    """
    # TODO: replace with celery's built in exponential backoff

    # 2 to the power of x. 1, 2, 4, 8, 16, 32, ...
    delay = 2**retry_count
    # never wait longer than 5 minutes
    return min(delay, 300)


def check_provider_message_should_retry(broadcast_provider_message):
    this_event = broadcast_provider_message.broadcast_event

    if this_event.transmitted_finishes_at < datetime.utcnow():
        print(this_event.transmitted_finishes_at, datetime.utcnow(),)
        raise MaxRetriesExceededError(
            f'Given up sending broadcast_event {this_event.id} ' +
            f'to provider {broadcast_provider_message.provider}: ' +
            f'The expiry time of {this_event.transmitted_finishes_at} has already passed'
        )

    newest_event = max(this_event.broadcast_message.events, key=lambda x: x.sent_at)

    if this_event != newest_event:
        raise MaxRetriesExceededError(
            f'Given up sending broadcast_event {this_event.id} ' +
            f'to provider {broadcast_provider_message.provider}: ' +
            f'This event has been superceeded by {newest_event.message_type} broadcast_event {newest_event.id}'
        )


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
            queue=QueueNames.BROADCASTS
        )


# max_retries=None: retry forever
@notify_celery.task(bind=True, name="send-broadcast-provider-message", max_retries=None)
@statsd(namespace="tasks")
def send_broadcast_provider_message(self, broadcast_event_id, provider):
    broadcast_event = dao_get_broadcast_event_by_id(broadcast_event_id)

    broadcast_provider_message = create_broadcast_provider_message(broadcast_event, provider)
    formatted_message_number = None
    if provider == BroadcastProvider.VODAFONE:
        formatted_message_number = format_sequential_number(broadcast_provider_message.message_number)

    current_app.logger.info(
        f'invoking cbc proxy to send '
        f'broadcast_event {broadcast_event.reference} '
        f'msgType {broadcast_event.message_type}'
    )

    areas = [
        {"polygon": polygon}
        for polygon in broadcast_event.transmitted_areas["simple_polygons"]
    ]

    channel = "test"
    if broadcast_event.service.broadcast_channel:
        channel = broadcast_event.service.broadcast_channel

    cbc_proxy_provider_client = cbc_proxy_client.get_proxy(provider)

    try:
        if broadcast_event.message_type == BroadcastEventMessageType.ALERT:
            cbc_proxy_provider_client.create_and_send_broadcast(
                identifier=str(broadcast_provider_message.id),
                message_number=formatted_message_number,
                headline="GOV.UK Notify Broadcast",
                description=broadcast_event.transmitted_content['body'],
                areas=areas,
                sent=broadcast_event.sent_at_as_cap_datetime_string,
                expires=broadcast_event.transmitted_finishes_at_as_cap_datetime_string,
                channel=channel
            )
        elif broadcast_event.message_type == BroadcastEventMessageType.UPDATE:
            cbc_proxy_provider_client.update_and_send_broadcast(
                identifier=str(broadcast_provider_message.id),
                message_number=formatted_message_number,
                headline="GOV.UK Notify Broadcast",
                description=broadcast_event.transmitted_content['body'],
                areas=areas,
                previous_provider_messages=broadcast_event.get_earlier_provider_messages(provider),
                sent=broadcast_event.sent_at_as_cap_datetime_string,
                expires=broadcast_event.transmitted_finishes_at_as_cap_datetime_string,
                # We think an alert update should always go out on the same channel that created the alert
                # We recognise there is a small risk with this code here that if the services channel was
                # changed between an alert being sent out and then updated, then something might go wrong
                # but we are relying on service channels changing almost never, and not mid incident
                # We may consider in the future, changing this such that we store the channel a broadcast was
                # sent on on the broadcast message itself and pick the value from there instead of the service
                channel=channel
            )
        elif broadcast_event.message_type == BroadcastEventMessageType.CANCEL:
            cbc_proxy_provider_client.cancel_broadcast(
                identifier=str(broadcast_provider_message.id),
                message_number=formatted_message_number,
                previous_provider_messages=broadcast_event.get_earlier_provider_messages(provider),
                sent=broadcast_event.sent_at_as_cap_datetime_string,
            )
    except CBCProxyRetryableException as exc:
        # this will raise MaxRetriesExceededError if we no longer want to retry
        # (because the message has expired)
        check_provider_message_should_retry(broadcast_provider_message)

        self.retry(
            exc=exc,
            countdown=get_retry_delay(self.request.retries),
            queue=QueueNames.BROADCASTS,
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
