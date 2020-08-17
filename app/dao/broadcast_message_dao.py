from app.models import BroadcastMessage, BroadcastEvent


def dao_get_broadcast_message_by_id_and_service_id(broadcast_message_id, service_id):
    return BroadcastMessage.query.filter(
        BroadcastMessage.id == broadcast_message_id,
        BroadcastMessage.service_id == service_id
    ).one()


def dao_get_broadcast_message_by_id(broadcast_message_id):
    return BroadcastMessage.query.get(broadcast_message_id)


def dao_get_broadcast_event_by_id(broadcast_event_id):
    return BroadcastEvent.query.get(broadcast_event_id)


def dao_get_broadcast_messages_for_service(service_id):
    return BroadcastMessage.query.filter(
        BroadcastMessage.service_id == service_id
    ).order_by(BroadcastMessage.created_at)


def get_earlier_events_for_broadcast_event(broadcast_event_id):
    """
    This is used to build up the references list.
    """
    this_event = BroadcastEvent.query.get(broadcast_event_id)

    return BroadcastEvent.query.filter(
        BroadcastEvent.broadcast_message_id == this_event.broadcast_message_id,
        BroadcastEvent.sent_at < this_event.sent_at
    ).order_by(
        BroadcastEvent.sent_at.asc()
    ).all()
