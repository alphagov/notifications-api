from app import db
from app.dao.dao_utils import transactional
from app.models import BroadcastMessage, BroadcastEvent, BroadcastProviderMessage, BroadcastProviderMessageStatus


def dao_get_broadcast_message_by_id_and_service_id(broadcast_message_id, service_id):
    return BroadcastMessage.query.filter(
        BroadcastMessage.id == broadcast_message_id,
        BroadcastMessage.service_id == service_id
    ).one()


def dao_get_broadcast_event_by_id(broadcast_event_id):
    return BroadcastEvent.query.filter(BroadcastEvent.id == broadcast_event_id).one()


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


@transactional
def create_broadcast_provider_message(broadcast_event, provider):
    provider_message = BroadcastProviderMessage(
        broadcast_event=broadcast_event,
        provider=provider,
        status=BroadcastProviderMessageStatus.SENDING,
    )
    db.session.add(provider_message)
    return provider_message
