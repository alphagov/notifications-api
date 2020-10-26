from flask import current_app
from notifications_utils.statsd_decorators import statsd

from app import cbc_proxy_client, notify_celery

from app.models import BroadcastEventMessageType
from app.dao.broadcast_message_dao import dao_get_broadcast_event_by_id


@notify_celery.task(name="send-broadcast-event")
@statsd(namespace="tasks")
def send_broadcast_event(broadcast_event_id):
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
        )
    elif broadcast_event.message_type == BroadcastEventMessageType.UPDATE:
        cbc_proxy_client.update_and_send_broadcast(
            identifier=str(broadcast_event.id),
            headline="GOV.UK Notify Broadcast",
            description=broadcast_event.transmitted_content['body'],
            areas=areas,
            references=broadcast_event.get_earlier_message_references(),
        )
    elif broadcast_event.message_type == BroadcastEventMessageType.CANCEL:
        cbc_proxy_client.cancel_broadcast(
            identifier=str(broadcast_event.id),
            headline="GOV.UK Notify Broadcast",
            description=broadcast_event.transmitted_content['body'],
            areas=areas,
            references=broadcast_event.get_earlier_message_references(),
        )
