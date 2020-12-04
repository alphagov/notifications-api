from datetime import datetime

from app.models import BROADCAST_TYPE, BroadcastEventMessageType
from app.dao.broadcast_message_dao import get_earlier_events_for_broadcast_event, create_broadcast_provider_message

from tests.app.db import create_broadcast_message, create_template, create_broadcast_event


def test_get_earlier_events_for_broadcast_event(sample_service):
    t = create_template(sample_service, BROADCAST_TYPE)
    bm = create_broadcast_message(t)

    events = [
        create_broadcast_event(
            bm,
            sent_at=datetime(2020, 1, 1, 12, 0, 0),
            message_type=BroadcastEventMessageType.ALERT,
            transmitted_content={'body': 'Initial content'}
        ),
        create_broadcast_event(
            bm,
            sent_at=datetime(2020, 1, 1, 13, 0, 0),
            message_type=BroadcastEventMessageType.UPDATE,
            transmitted_content={'body': 'Updated content'}
        ),
        create_broadcast_event(
            bm,
            sent_at=datetime(2020, 1, 1, 14, 0, 0),
            message_type=BroadcastEventMessageType.UPDATE,
            transmitted_content={'body': 'Updated content'},
            transmitted_areas=['wales']
        ),
        create_broadcast_event(
            bm,
            sent_at=datetime(2020, 1, 1, 15, 0, 0),
            message_type=BroadcastEventMessageType.CANCEL,
            transmitted_finishes_at=datetime(2020, 1, 1, 15, 0, 0),
        )
    ]

    # only fetches earlier events, and they're in time order
    earlier_events = get_earlier_events_for_broadcast_event(events[2].id)
    assert earlier_events == [events[0], events[1]]


def test_create_broadcast_provider_message_creates_in_correct_state(sample_broadcast_service):
    t = create_template(sample_broadcast_service, BROADCAST_TYPE)
    broadcast_message = create_broadcast_message(t)
    broadcast_event = create_broadcast_event(
        broadcast_message,
        sent_at=datetime(2020, 1, 1, 12, 0, 0),
        message_type=BroadcastEventMessageType.ALERT,
        transmitted_content={'body': 'Initial content'}
    )

    broadcast_provider_message, message_number = create_broadcast_provider_message(broadcast_event, 'fake-provider')

    assert broadcast_provider_message.status == 'sending'
    assert broadcast_provider_message.broadcast_event_id == broadcast_event.id
    assert broadcast_provider_message.created_at is not None
    assert broadcast_provider_message.updated_at is None
