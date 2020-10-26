from freezegun import freeze_time
import pytest

from app.models import BROADCAST_TYPE, BroadcastStatusType, BroadcastEventMessageType
from app.celery.broadcast_message_tasks import send_broadcast_event
from tests.app.db import create_template, create_broadcast_message, create_broadcast_event


@freeze_time('2020-08-01 12:00')
def test_create_broadcast_event_sends_data_correctly(mocker, sample_service):
    template = create_template(sample_service, BROADCAST_TYPE)
    broadcast_message = create_broadcast_message(
        template,
        areas={
            'areas': ['london', 'glasgow'],
            'simple_polygons': [
                [[50.12, 1.2], [50.13, 1.2], [50.14, 1.21]],
                [[-4.53, 55.72], [-3.88, 55.72], [-3.88, 55.96], [-4.53, 55.96]],
            ],
        },
        status=BroadcastStatusType.BROADCASTING
    )
    event = create_broadcast_event(broadcast_message)

    mock_create_broadcast = mocker.patch(
        'app.cbc_proxy_client.create_and_send_broadcast',
    )

    send_broadcast_event(broadcast_event_id=str(event.id))

    mock_create_broadcast.assert_called_once_with(
        identifier=str(event.id),
        headline='GOV.UK Notify Broadcast',
        description='this is an emergency broadcast message',
        areas=[{
            'polygon': [
                [50.12, 1.2], [50.13, 1.2], [50.14, 1.21],
            ],
        }, {
            'polygon': [
                [-4.53, 55.72], [-3.88, 55.72], [-3.88, 55.96], [-4.53, 55.96],
            ],
        }],
    )


def test_update_broadcast_event_sends_references(mocker, sample_service):
    template = create_template(sample_service, BROADCAST_TYPE, content='content')

    broadcast_message = create_broadcast_message(
        template,
        areas={
            'areas': ['london'],
            'simple_polygons': [
                [[50.12, 1.2], [50.13, 1.2], [50.14, 1.21]],
            ],
        },
        status=BroadcastStatusType.BROADCASTING
    )

    alert_event = create_broadcast_event(broadcast_message, message_type=BroadcastEventMessageType.ALERT)
    update_event = create_broadcast_event(broadcast_message, message_type=BroadcastEventMessageType.UPDATE)

    mock_update_broadcast = mocker.patch(
        'app.cbc_proxy_client.update_and_send_broadcast',
    )

    send_broadcast_event(broadcast_event_id=str(update_event.id))

    mock_update_broadcast.assert_called_once_with(
        identifier=str(update_event.id),
        headline="GOV.UK Notify Broadcast",
        description='this is an emergency broadcast message',
        areas=[{
            "polygon": [[50.12, 1.2], [50.13, 1.2], [50.14, 1.21]],
        }],
        references=[alert_event.reference],
    )


def test_cancel_broadcast_event_sends_references(mocker, sample_service):
    template = create_template(sample_service, BROADCAST_TYPE, content='content')

    broadcast_message = create_broadcast_message(
        template,
        areas={
            'areas': ['london'],
            'simple_polygons': [
                [[50.12, 1.2], [50.13, 1.2], [50.14, 1.21]],
            ],
        },
        status=BroadcastStatusType.BROADCASTING
    )

    alert_event = create_broadcast_event(broadcast_message, message_type=BroadcastEventMessageType.ALERT)
    update_event = create_broadcast_event(broadcast_message, message_type=BroadcastEventMessageType.UPDATE)
    cancel_event = create_broadcast_event(broadcast_message, message_type=BroadcastEventMessageType.CANCEL)

    mock_cancel_broadcast = mocker.patch(
        'app.cbc_proxy_client.cancel_broadcast',
    )

    send_broadcast_event(broadcast_event_id=str(cancel_event.id))

    mock_cancel_broadcast.assert_called_once_with(
        identifier=str(cancel_event.id),
        headline="GOV.UK Notify Broadcast",
        description='this is an emergency broadcast message',
        areas=[{
            "polygon": [[50.12, 1.2], [50.13, 1.2], [50.14, 1.21]],
        }],
        references=[alert_event.reference, update_event.reference],
    )


def test_send_broadcast_event_errors(mocker, sample_service):
    template = create_template(sample_service, BROADCAST_TYPE)

    broadcast_message = create_broadcast_message(
        template,
        areas={
            'areas': ['london'],
            'simple_polygons': [
                [[50.12, 1.2], [50.13, 1.2], [50.14, 1.21]],
            ],
        },
        status=BroadcastStatusType.BROADCASTING
    )

    event = create_broadcast_event(broadcast_message)

    mock_create_broadcast = mocker.patch(
        'app.cbc_proxy_client.create_and_send_broadcast',
        side_effect=Exception('oh no'),
    )

    with pytest.raises(Exception) as ex:
        send_broadcast_event(broadcast_event_id=str(event.id))

    assert ex.match('oh no')

    mock_create_broadcast.assert_called_once_with(
        identifier=str(event.id),
        headline="GOV.UK Notify Broadcast",
        description='this is an emergency broadcast message',
        areas=[{
            'polygon': [
                [50.12, 1.2],
                [50.13, 1.2],
                [50.14, 1.21],
            ],
        }],
    )
