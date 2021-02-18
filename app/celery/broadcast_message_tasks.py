import uuid
from datetime import datetime

from flask import current_app
from notifications_utils.statsd_decorators import statsd
from sqlalchemy.schema import Sequence

from app import cbc_proxy_client, db, notify_celery
from app.clients.cbc_proxy import CBCProxyFatalException, CBCProxyRetryableException
from app.config import QueueNames
from app.models import BroadcastEventMessageType, BroadcastProvider, BroadcastProviderMessageStatus
from app.dao.broadcast_message_dao import (
    dao_get_broadcast_event_by_id,
    create_broadcast_provider_message,
    update_broadcast_provider_message_status
)

from app.utils import format_sequential_number


def get_retry_delay(retry_count):
    """
    Given a count of retries so far, return a delay for the next one.
    `retry_count` should be 0 the first time a task fails.
    """
    # TODO: replace with celery's built in exponential backoff

    # 2 to the power of x. 1, 2, 4, 8, 16, 32, ...
    delay = 2**retry_count
    # never wait longer than 4 minutes
    return min(delay, 240)


def check_provider_message_should_send(broadcast_event, provider):
    """
    If any previous event hasn't sent yet for that provider, then we shouldn't send the current event. Instead, fail and
    raise a P1 - so that a notify team member can assess the state of the previous messages, and if necessary, can
    replay the `send_broadcast_provider_message` task if the previous message has now been sent.

    Note: This is called before the new broadcast_provider_message is created.

    # Help, I've come across this code following a pagerduty alert, what should I do?

    1. Find the failing broadcast_provider_message associated with the previous event that caused this to trip.
    2. If that provider message is still failing to send, fix the issue causing that. The task to send that previous
       message might still be retrying in the background - look for logs related to that task.
    3. If that provider message has sent succesfully, you might need to send this task off depending on context. This
       might not always be true though, for example, it may not be necessary to send a cancel if the original alert has
       already expired.
    4. If you need to re-send this task off again, you'll need to run the following command on paas:
       `send_broadcast_provider_message.apply_async(args=(broadcast_event_id, provider), queue=QueueNames.BROADCASTS)`
    """
    current_provider_message = broadcast_event.get_provider_message(provider)
    # if this is the first time a task is being executed, it won't have a provider message yet
    if current_provider_message and current_provider_message.status != BroadcastProviderMessageStatus.SENDING:
        raise CBCProxyFatalException(
            f'Cannot send broadcast_event {broadcast_event.id} ' +
            f'to provider {provider}: ' +
            f'It is in status {current_provider_message.status}'
        )

    if broadcast_event.transmitted_finishes_at < datetime.utcnow():
        # TODO: This should be a different kind of exception to distinguish "We should know something went wrong, but
        # no immediate action" from "We need to fix this immediately"
        raise CBCProxyFatalException(
            f'Cannot send broadcast_event {broadcast_event.id} ' +
            f'to provider {provider}: ' +
            f'The expiry time of {broadcast_event.transmitted_finishes_at} has already passed'
        )

    # get events sorted from earliest to latest
    events = sorted(broadcast_event.broadcast_message.events, key=lambda x: x.sent_at)

    for prev_event in events:
        if prev_event.id != broadcast_event.id and prev_event.sent_at < broadcast_event.sent_at:
            # get the record from when that event was sent to the same provider
            prev_provider_message = prev_event.get_provider_message(provider)

            # the previous message hasn't even got round to running `send_broadcast_provider_message` yet.
            if not prev_provider_message:
                raise CBCProxyFatalException(
                    f'Cannot send {broadcast_event.id}. Previous event {prev_event.id} ' +
                    f'(type {prev_event.message_type}) has no provider_message for provider {provider} yet.\n' +
                    'You must ensure that the other event sends succesfully, then manually kick off this event ' +
                    'again by re-running send_broadcast_provider_message for this event and provider.'
                )

            # if there's a previous message that has started but not finished sending (whether it fatally errored or is
            # currently retrying)
            if prev_provider_message.status != BroadcastProviderMessageStatus.ACK:
                raise CBCProxyFatalException(
                    f'Cannot send {broadcast_event.id}. Previous event {prev_event.id} ' +
                    f'(type {prev_event.message_type}) has not finished sending to provider {provider} yet.\n' +
                    f'It is currently in status "{prev_provider_message.status}".\n' +
                    'You must ensure that the other event sends succesfully, then manually kick off this event ' +
                    'again by re-running send_broadcast_provider_message for this event and provider.'
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

    check_provider_message_should_send(broadcast_event, provider)

    # the broadcast_provider_message may already exist if we retried previously
    broadcast_provider_message = broadcast_event.get_provider_message(provider)
    if broadcast_provider_message is None:
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
        delay = get_retry_delay(self.request.retries)
        current_app.logger.exception(
            f'Retrying send_broadcast_provider_message for broadcast_event {broadcast_event_id} and ' +
            f'provider {provider} in {delay} seconds'
        )

        self.retry(
            exc=exc,
            countdown=delay,
            queue=QueueNames.BROADCASTS,
        )

    update_broadcast_provider_message_status(broadcast_provider_message, status=BroadcastProviderMessageStatus.ACK)


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
