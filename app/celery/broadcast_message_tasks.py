import requests
from flask import current_app
from notifications_utils.statsd_decorators import statsd

from app import notify_celery

from app.dao.broadcast_message_dao import dao_get_broadcast_event_by_id


@notify_celery.task(name="send-broadcast-event")
@statsd(namespace="tasks")
def send_broadcast_event(broadcast_event_id, provider='stub-1'):
    broadcast_event = dao_get_broadcast_event_by_id(broadcast_event_id)

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
