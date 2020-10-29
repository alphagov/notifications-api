import uuid

from flask import current_app
from notifications_utils.statsd_decorators import statsd

from app import cbc_proxy_client, notify_celery
from app.config import QueueNames
from app.models import BroadcastEventMessageType, BroadcastProvider
from app.dao.broadcast_message_dao import dao_get_broadcast_event_by_id


@notify_celery.task(name="send-broadcast-event")
@statsd(namespace="tasks")
def send_broadcast_event(broadcast_event_id):
    for provider in BroadcastProvider.PROVIDERS:
        # TODO: Decide whether to send to each provider based on platform admin, service level settings, broadcast
        # level settings, etc.
        send_broadcast_provider_message.apply_async(
            kwargs={'broadcast_event_id': broadcast_event_id, 'provider': provider},
            queue=QueueNames.NOTIFY
        )


@notify_celery.task(name="send-broadcast-provider-message")
@statsd(namespace="tasks")
def send_broadcast_provider_message(broadcast_event_id, provider):
    broadcast_event = dao_get_broadcast_event_by_id(broadcast_event_id)

    current_app.logger.info(
        f'invoking cbc proxy to send '
        f'broadcast_event {broadcast_event.reference} '
        f'msgType {broadcast_event.message_type}'
    )

    areas = [
        {"polygon": polygon}
        for polygon in broadcast_event.transmitted_areas["simple_polygons"]
    ]

    if broadcast_event.message_type == BroadcastEventMessageType.ALERT:
        cbc_proxy_client.create_and_send_broadcast(
            identifier=str(broadcast_event.id),
            headline="GOV.UK Notify Broadcast",
            description=broadcast_event.transmitted_content['body'],
            areas=areas,
            sent=broadcast_event.sent_at_as_cap_datetime_string,
            expires=broadcast_event.transmitted_finishes_at_as_cap_datetime_string,
        )
    elif broadcast_event.message_type == BroadcastEventMessageType.UPDATE:
        cbc_proxy_client.update_and_send_broadcast(
            identifier=str(broadcast_event.id),
            headline="GOV.UK Notify Broadcast",
            description=broadcast_event.transmitted_content['body'],
            areas=areas,
            references=broadcast_event.get_earlier_message_references(),
            sent=broadcast_event.sent_at_as_cap_datetime_string,
            expires=broadcast_event.transmitted_finishes_at_as_cap_datetime_string,
        )
    elif broadcast_event.message_type == BroadcastEventMessageType.CANCEL:
        cbc_proxy_client.cancel_broadcast(
            identifier=str(broadcast_event.id),
            headline="GOV.UK Notify Broadcast",
            description=broadcast_event.transmitted_content['body'],
            areas=areas,
            references=broadcast_event.get_earlier_message_references(),
            sent=broadcast_event.sent_at_as_cap_datetime_string,
            expires=broadcast_event.transmitted_finishes_at_as_cap_datetime_string,
        )


@notify_celery.task(name='trigger-link-test')
def trigger_link_test(provider):
    """
    Currently we only have one hardcoded CBC Proxy, which corresponds to one
    CBC, and so currently we do not specify the CBC Proxy name

    In future we will have multiple CBC proxies, each proxy corresponding to
    one MNO's CBC

    This task should invoke other tasks which do the actual link tests, eg:
    for cbc_name in app.config.ENABLED_CBCS:
        send_link_test_for_cbc(cbc_name)

    Alternatively this task could be configured to be a Celery group
    """
    identifier = str(uuid.uuid4())
    message = f"Sending a link test to CBC proxy for provider {provider} with ID {identifier}"
    current_app.logger.info(message)
    cbc_proxy_client.send_link_test(identifier)
