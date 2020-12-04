import uuid
from unittest.mock import call, ANY

from freezegun import freeze_time
import pytest

from app.models import (
    BROADCAST_TYPE,
    BroadcastStatusType,
    BroadcastEventMessageType,
    BroadcastProviderMessageStatus,
    ServiceBroadcastProviderRestriction
)
from app.celery.broadcast_message_tasks import send_broadcast_event, send_broadcast_provider_message, trigger_link_test

from tests.app.db import (
    create_template,
    create_broadcast_message,
    create_broadcast_event,
    create_broadcast_provider_message
)
from tests.conftest import set_config


def test_send_broadcast_event_queues_up_for_active_providers(mocker, notify_api, sample_service):
    template = create_template(sample_service, BROADCAST_TYPE)
    broadcast_message = create_broadcast_message(template, status=BroadcastStatusType.BROADCASTING)
    event = create_broadcast_event(broadcast_message)

    mock_send_broadcast_provider_message = mocker.patch(
        'app.celery.broadcast_message_tasks.send_broadcast_provider_message',
    )

    with set_config(notify_api, 'ENABLED_CBCS', ['ee', 'vodafone']):
        send_broadcast_event(event.id)

    assert mock_send_broadcast_provider_message.apply_async.call_args_list == [
        call(kwargs={'broadcast_event_id': event.id, 'provider': 'ee'}, queue='notify-internal-tasks'),
        call(kwargs={'broadcast_event_id': event.id, 'provider': 'vodafone'}, queue='notify-internal-tasks')
    ]


def test_send_broadcast_event_only_sends_to_one_provider_if_set_on_service(
    mocker,
    notify_db,
    notify_api,
    sample_service
):
    notify_db.session.add(ServiceBroadcastProviderRestriction(
        service=sample_service,
        provider='vodafone'
    ))

    template = create_template(sample_service, BROADCAST_TYPE)
    broadcast_message = create_broadcast_message(template, status=BroadcastStatusType.BROADCASTING)
    event = create_broadcast_event(broadcast_message)

    mock_send_broadcast_provider_message = mocker.patch(
        'app.celery.broadcast_message_tasks.send_broadcast_provider_message',
    )

    with set_config(notify_api, 'ENABLED_CBCS', ['ee', 'vodafone']):
        send_broadcast_event(event.id)

    assert mock_send_broadcast_provider_message.apply_async.call_args_list == [
        call(kwargs={'broadcast_event_id': event.id, 'provider': 'vodafone'}, queue='notify-internal-tasks')
    ]


def test_send_broadcast_event_does_nothing_if_provider_set_on_service_isnt_enabled_globally(
    mocker,
    notify_db,
    notify_api,
    sample_service
):
    notify_db.session.add(ServiceBroadcastProviderRestriction(
        service=sample_service,
        provider='three'
    ))

    template = create_template(sample_service, BROADCAST_TYPE)
    broadcast_message = create_broadcast_message(template, status=BroadcastStatusType.BROADCASTING)
    event = create_broadcast_event(broadcast_message)

    mock_send_broadcast_provider_message = mocker.patch(
        'app.celery.broadcast_message_tasks.send_broadcast_provider_message',
    )

    with set_config(notify_api, 'ENABLED_CBCS', ['ee', 'vodafone']):
        send_broadcast_event(event.id)

    assert mock_send_broadcast_provider_message.apply_async.called is False


def test_send_broadcast_event_does_nothing_if_cbc_proxy_disabled(mocker, notify_api):
    mock_send_broadcast_provider_message = mocker.patch(
        'app.celery.broadcast_message_tasks.send_broadcast_provider_message',
    )

    event_id = uuid.uuid4()
    with set_config(notify_api, 'ENABLED_CBCS', ['ee', 'vodafone']), set_config(notify_api, 'CBC_PROXY_ENABLED', False):
        send_broadcast_event(event_id)

    assert mock_send_broadcast_provider_message.apply_async.called is False


@freeze_time('2020-08-01 12:00')
def test_send_broadcast_provider_message_sends_data_correctly(mocker, sample_service):
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
        'app.clients.cbc_proxy.CBCProxyEE.create_and_send_broadcast',
    )

    assert event.get_provider_message('ee') is None

    send_broadcast_provider_message(provider='ee', broadcast_event_id=str(event.id))

    broadcast_provider_message = event.get_provider_message('ee')
    assert broadcast_provider_message.status == BroadcastProviderMessageStatus.SENDING

    mock_create_broadcast.assert_called_once_with(
        identifier=str(broadcast_provider_message.id),
        message_number=mocker.ANY,
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
        sent=event.sent_at_as_cap_datetime_string,
        expires=event.transmitted_finishes_at_as_cap_datetime_string,
    )


def test_send_broadcast_provider_message_sends_update_with_references(mocker, sample_service):
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
    create_broadcast_provider_message(alert_event, 'ee')
    update_event = create_broadcast_event(broadcast_message, message_type=BroadcastEventMessageType.UPDATE)

    mock_update_broadcast = mocker.patch(
        'app.clients.cbc_proxy.CBCProxyEE.update_and_send_broadcast',
    )

    send_broadcast_provider_message(provider='ee', broadcast_event_id=str(update_event.id))

    broadcast_provider_message = update_event.get_provider_message('ee')
    assert broadcast_provider_message.status == BroadcastProviderMessageStatus.SENDING

    mock_update_broadcast.assert_called_once_with(
        identifier=str(broadcast_provider_message.id),
        message_number=mocker.ANY,
        headline="GOV.UK Notify Broadcast",
        description='this is an emergency broadcast message',
        areas=[{
            "polygon": [[50.12, 1.2], [50.13, 1.2], [50.14, 1.21]],
        }],
        previous_provider_messages=[
            alert_event.get_provider_message('ee')
        ],
        sent=update_event.sent_at_as_cap_datetime_string,
        expires=update_event.transmitted_finishes_at_as_cap_datetime_string,
    )


def test_send_broadcast_provider_message_sends_cancel_with_references(mocker, sample_service):
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

    create_broadcast_provider_message(alert_event, 'ee')
    create_broadcast_provider_message(update_event, 'ee')

    mock_cancel_broadcast = mocker.patch(
        'app.clients.cbc_proxy.CBCProxyEE.cancel_broadcast',
    )

    send_broadcast_provider_message(provider='ee', broadcast_event_id=str(cancel_event.id))

    broadcast_provider_message = cancel_event.get_provider_message('ee')
    assert broadcast_provider_message.status == BroadcastProviderMessageStatus.SENDING

    mock_cancel_broadcast.assert_called_once_with(
        identifier=str(broadcast_provider_message.id),
        message_number=mocker.ANY,
        headline="GOV.UK Notify Broadcast",
        description='this is an emergency broadcast message',
        areas=[{
            "polygon": [[50.12, 1.2], [50.13, 1.2], [50.14, 1.21]],
        }],
        previous_provider_messages=[
            alert_event.get_provider_message('ee'),
            update_event.get_provider_message('ee')
        ],
        sent=cancel_event.sent_at_as_cap_datetime_string,
        expires=cancel_event.transmitted_finishes_at_as_cap_datetime_string,
    )


def test_send_broadcast_provider_message_errors(mocker, sample_service):
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
        'app.clients.cbc_proxy.CBCProxyEE.create_and_send_broadcast',
        side_effect=Exception('oh no'),
    )

    with pytest.raises(Exception) as ex:
        send_broadcast_provider_message(provider='ee', broadcast_event_id=str(event.id))

    assert ex.match('oh no')

    mock_create_broadcast.assert_called_once_with(
        identifier=ANY,
        message_number=mocker.ANY,
        headline="GOV.UK Notify Broadcast",
        description='this is an emergency broadcast message',
        areas=[{
            'polygon': [
                [50.12, 1.2],
                [50.13, 1.2],
                [50.14, 1.21],
            ],
        }],
        sent=event.sent_at_as_cap_datetime_string,
        expires=event.transmitted_finishes_at_as_cap_datetime_string,
    )


@pytest.mark.parametrize("provider,provider_capitalised", [
    ["ee", "EE"],
    ["vodafone", "Vodafone"]
])
def test_trigger_link_tests_invokes_cbc_proxy_client(
    mocker, provider, provider_capitalised
):
    mock_send_link_test = mocker.patch(
        f'app.clients.cbc_proxy.CBCProxy{provider_capitalised}.send_link_test',
    )

    trigger_link_test(provider)

    assert mock_send_link_test.called
    # the 0th argument of the call to send_link_test
    identifier = mock_send_link_test.mock_calls[0][1][0]

    try:
        uuid.UUID(identifier)
    except BaseException:
        pytest.fail(f"{identifier} is not a valid uuid")

    # testing sequential number:
    if provider == 'vodafone':
        assert type(mock_send_link_test.mock_calls[0][1][1]) is str
        assert len(mock_send_link_test.mock_calls[0][1][1]) == 8
    else:
        assert not mock_send_link_test.mock_calls[0][1][1]
