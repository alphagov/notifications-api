import requests
from flask import current_app
from notifications_utils.statsd_decorators import statsd

from app import cbc_proxy_client, notify_celery

from app.models import BroadcastEventMessageType
from app.dao.broadcast_message_dao import dao_get_broadcast_event_by_id


@notify_celery.task(name="send-broadcast-event")
@statsd(namespace="tasks")
def send_broadcast_event(broadcast_event_id, provider='stub-1'):
    broadcast_event = dao_get_broadcast_event_by_id(broadcast_event_id)

    if broadcast_event.message_type == BroadcastEventMessageType.ALERT:
        current_app.logger.info(
            f'invoking cbc proxy to send '
            f'broadcast_event {broadcast_event.reference} '
            f'msgType {broadcast_event.message_type} to {provider}'
        )

        cbc_proxy_client.create_and_send_broadcast(
            identifier=str(broadcast_event.id),
            headline="GOV.UK Notify Broadcast",
            description=broadcast_event.transmitted_content['body'],
        )

    current_app.logger.info(
        f'sending broadcast_event {broadcast_event.reference} '
        f'msgType {broadcast_event.message_type} to {provider}'
    )

    payload = broadcast_event.serialize()

    resp = requests.post(
        f'{current_app.config["CBC_PROXY_URL"]}/broadcasts/events/{provider}',
        json=payload
    )
    resp.raise_for_status()

    current_app.logger.info(
        f'broadcast_event {broadcast_event.reference} '
        f'msgType {broadcast_event.message_type} sent to {provider}'
    )
