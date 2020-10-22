from freezegun import freeze_time
import pytest
import requests_mock
from requests import RequestException

from app.models import BROADCAST_TYPE, BroadcastStatusType, BroadcastEventMessageType
from app.celery.broadcast_message_tasks import send_broadcast_event
from tests.app.db import create_template, create_broadcast_message, create_broadcast_event


@freeze_time('2020-08-01 12:00')
def test_send_broadcast_event_sends_data_correctly(mocker, sample_service):
    template = create_template(sample_service, BROADCAST_TYPE)
    broadcast_message = create_broadcast_message(
        template,
        areas={"areas": ['london'], "simple_polygons": [[[50.12, 1.2], [50.13, 1.2], [50.14, 1.21]]]},
        status=BroadcastStatusType.BROADCASTING
    )
    event = create_broadcast_event(broadcast_message)

    mock_create_broadcast = mocker.patch(
        'app.cbc_proxy_client.create_and_send_broadcast',
    )

    with requests_mock.Mocker() as request_mock:
        request_mock.post("http://test-cbc-proxy/broadcasts/events/stub-1", json={'valid': 'true'}, status_code=200)
        send_broadcast_event(broadcast_event_id=str(event.id))

    mock_create_broadcast.assert_called_once_with(
        identifier=str(event.id),
        headline="GOV.UK Notify Broadcast",
        description='this is an emergency broadcast message',
    )

    assert request_mock.call_count == 1
    assert request_mock.request_history[0].method == 'POST'
    assert request_mock.request_history[0].headers["Content-type"] == "application/json"

    cbc_json = request_mock.request_history[0].json()
    assert cbc_json['id'] == str(event.id)
    assert cbc_json['broadcast_message_id'] == str(broadcast_message.id)
    assert cbc_json['sent_at'] == '2020-08-01T12:00:00.000000Z'
    assert cbc_json['transmitted_starts_at'] is None
    assert cbc_json['transmitted_areas'] == {
        "areas": ['london'], "simple_polygons": [[[50.12, 1.2], [50.13, 1.2], [50.14, 1.21]]]
    }


def test_send_broadcast_event_sends_references(mocker, sample_service):
    template = create_template(sample_service, BROADCAST_TYPE, content='content')
    broadcast_message = create_broadcast_message(template, areas=['london'], status=BroadcastStatusType.BROADCASTING)
    alert_event = create_broadcast_event(broadcast_message, message_type=BroadcastEventMessageType.ALERT)
    cancel_event = create_broadcast_event(broadcast_message, message_type=BroadcastEventMessageType.CANCEL)

    mock_create_broadcast = mocker.patch(
        'app.cbc_proxy_client.create_and_send_broadcast',
    )

    with requests_mock.Mocker() as request_mock:
        request_mock.post("http://test-cbc-proxy/broadcasts/events/stub-1", json={'valid': 'true'}, status_code=200)
        send_broadcast_event(broadcast_event_id=str(cancel_event.id))

    assert not mock_create_broadcast.called

    assert request_mock.call_count == 1
    assert request_mock.request_history[0].method == 'POST'
    assert request_mock.request_history[0].headers["Content-type"] == "application/json"

    cbc_json = request_mock.request_history[0].json()
    assert cbc_json['id'] == str(cancel_event.id)
    assert cbc_json['message_type'] == cancel_event.message_type
    assert cbc_json['previous_event_references'] == [alert_event.reference]


def test_send_broadcast_event_errors(mocker, sample_service):
    template = create_template(sample_service, BROADCAST_TYPE)
    broadcast_message = create_broadcast_message(template, status=BroadcastStatusType.BROADCASTING)
    event = create_broadcast_event(broadcast_message)

    mock_create_broadcast = mocker.patch(
        'app.cbc_proxy_client.create_and_send_broadcast',
    )

    with requests_mock.Mocker() as request_mock:
        request_mock.post("http://test-cbc-proxy/broadcasts/events/stub-1", text='503 bad gateway', status_code=503)
        # we're not retrying or anything for the moment - but this'll ensure any exception gets logged
        with pytest.raises(RequestException) as ex:
            send_broadcast_event(broadcast_event_id=str(event.id))

    assert ex.value.response.status_code == 503

    mock_create_broadcast.assert_called_once_with(
        identifier=str(event.id),
        headline="GOV.UK Notify Broadcast",
        description='this is an emergency broadcast message',
    )
