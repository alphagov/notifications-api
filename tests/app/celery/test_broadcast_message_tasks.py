import uuid
from datetime import datetime
from unittest.mock import call, ANY

from freezegun import freeze_time
from celery.exceptions import MaxRetriesExceededError
import pytest

from app.models import (
    BROADCAST_TYPE,
    BroadcastStatusType,
    BroadcastEventMessageType,
    BroadcastProviderMessageStatus,
    ServiceBroadcastProviderRestriction,
    ServiceBroadcastSettings,
)
from app.clients.cbc_proxy import CBCProxyRetryableException
from app.celery.broadcast_message_tasks import (
    check_provider_message_should_retry,
    get_retry_delay,
    send_broadcast_event,
    send_broadcast_provider_message,
    trigger_link_test,
)

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
        call(kwargs={'broadcast_event_id': event.id, 'provider': 'ee'}, queue='broadcast-tasks'),
        call(kwargs={'broadcast_event_id': event.id, 'provider': 'vodafone'}, queue='broadcast-tasks')
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
        call(kwargs={'broadcast_event_id': event.id, 'provider': 'vodafone'}, queue='broadcast-tasks')
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
@pytest.mark.parametrize('provider,provider_capitalised', [
    ['ee', 'EE'],
    ['three', 'Three'],
    ['o2', 'O2'],
    ['vodafone', 'Vodafone'],
])
def test_send_broadcast_provider_message_sends_data_correctly(
    mocker, sample_service, provider, provider_capitalised
):
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
        f'app.clients.cbc_proxy.CBCProxy{provider_capitalised}.create_and_send_broadcast',
    )

    assert event.get_provider_message(provider) is None

    send_broadcast_provider_message(provider=provider, broadcast_event_id=str(event.id))

    broadcast_provider_message = event.get_provider_message(provider)
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
        channel="test",
    )


@freeze_time('2020-08-01 12:00')
@pytest.mark.parametrize('provider,provider_capitalised', [
    ['ee', 'EE'],
    ['three', 'Three'],
    ['o2', 'O2'],
    ['vodafone', 'Vodafone'],
])
@pytest.mark.parametrize('channel', ['test', 'severe'])
def test_send_broadcast_provider_message_uses_channel_set_on_broadcast_service(
    notify_db, mocker, sample_service, provider, provider_capitalised, channel
):
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
    notify_db.session.add(ServiceBroadcastSettings(service=sample_service, channel=channel))

    mock_create_broadcast = mocker.patch(
        f'app.clients.cbc_proxy.CBCProxy{provider_capitalised}.create_and_send_broadcast',
    )

    send_broadcast_provider_message(provider=provider, broadcast_event_id=str(event.id))

    mock_create_broadcast.assert_called_once_with(
        identifier=mocker.ANY,
        message_number=mocker.ANY,
        headline='GOV.UK Notify Broadcast',
        description='this is an emergency broadcast message',
        areas=mocker.ANY,
        sent=mocker.ANY,
        expires=mocker.ANY,
        channel=channel,
    )


@freeze_time('2020-08-01 12:00')
@pytest.mark.parametrize('provider,provider_capitalised', [
    ['ee', 'EE'],
    ['three', 'Three'],
    ['o2', 'O2'],
    ['vodafone', 'Vodafone'],
])
def test_send_broadcast_provider_message_defaults_to_test_channel_if_no_service_broadcast_settings(
    notify_db, mocker, sample_service, provider, provider_capitalised
):
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
        f'app.clients.cbc_proxy.CBCProxy{provider_capitalised}.create_and_send_broadcast',
    )

    send_broadcast_provider_message(provider=provider, broadcast_event_id=str(event.id))

    mock_create_broadcast.assert_called_once_with(
        identifier=mocker.ANY,
        message_number=mocker.ANY,
        headline='GOV.UK Notify Broadcast',
        description='this is an emergency broadcast message',
        areas=mocker.ANY,
        sent=mocker.ANY,
        expires=mocker.ANY,
        channel="test",
    )


def test_send_broadcast_provider_message_works_if_we_retried_previously(mocker, sample_service):
    template = create_template(sample_service, BROADCAST_TYPE)
    broadcast_message = create_broadcast_message(
        template,
        areas={'areas': [], 'simple_polygons': [],},
        status=BroadcastStatusType.BROADCASTING
    )
    event = create_broadcast_event(broadcast_message)

    # an existing provider message already exists, and previously failed
    existing_provider_message = create_broadcast_provider_message(
        broadcast_event=event,
        provider='ee',
        status=BroadcastProviderMessageStatus.TECHNICAL_FAILURE
    )

    mock_create_broadcast = mocker.patch(
        f'app.clients.cbc_proxy.CBCProxyEE.create_and_send_broadcast',
    )

    send_broadcast_provider_message(provider='ee', broadcast_event_id=str(event.id))

    # make sure we haven't completed a duplicate event - we shouldn't record the failure
    assert len(event.provider_messages) == 1

    broadcast_provider_message = event.get_provider_message('ee')
    # TODO: Should be ACK, and should have an updated_at
    assert broadcast_provider_message.status == BroadcastProviderMessageStatus.TECHNICAL_FAILURE
    assert broadcast_provider_message.updated_at is None

    mock_create_broadcast.assert_called_once_with(
        identifier=str(broadcast_provider_message.id),
        message_number=mocker.ANY,
        headline='GOV.UK Notify Broadcast',
        description='this is an emergency broadcast message',
        areas=[],
        sent=event.sent_at_as_cap_datetime_string,
        expires=event.transmitted_finishes_at_as_cap_datetime_string,
        channel='test',
    )


@freeze_time('2020-08-01 12:00')
@pytest.mark.parametrize('provider,provider_capitalised', [
    ['ee', 'EE'],
    ['three', 'Three'],
    ['o2', 'O2'],
    ['vodafone', 'Vodafone'],
])
def test_send_broadcast_provider_message_sends_data_correctly_when_broadcast_message_has_no_template(
    mocker, sample_service, provider, provider_capitalised
):
    broadcast_message = create_broadcast_message(
        service=sample_service,
        template=None,
        content='this is an emergency broadcast message',
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
        f'app.clients.cbc_proxy.CBCProxy{provider_capitalised}.create_and_send_broadcast',
    )

    send_broadcast_provider_message(provider=provider, broadcast_event_id=str(event.id))

    broadcast_provider_message = event.get_provider_message(provider)

    mock_create_broadcast.assert_called_once_with(
        identifier=str(broadcast_provider_message.id),
        message_number=mocker.ANY,
        headline='GOV.UK Notify Broadcast',
        description='this is an emergency broadcast message',
        areas=mocker.ANY,
        sent=mocker.ANY,
        expires=mocker.ANY,
        channel="test"
    )


@pytest.mark.parametrize('provider,provider_capitalised', [
    ['ee', 'EE'],
    ['three', 'Three'],
    ['o2', 'O2'],
    ['vodafone', 'Vodafone'],
])
def test_send_broadcast_provider_message_sends_update_with_references(
    mocker, sample_service, provider, provider_capitalised
):
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
    create_broadcast_provider_message(alert_event, provider)
    update_event = create_broadcast_event(broadcast_message, message_type=BroadcastEventMessageType.UPDATE)

    mock_update_broadcast = mocker.patch(
        f'app.clients.cbc_proxy.CBCProxy{provider_capitalised}.update_and_send_broadcast',
    )

    send_broadcast_provider_message(provider=provider, broadcast_event_id=str(update_event.id))

    broadcast_provider_message = update_event.get_provider_message(provider)
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
            alert_event.get_provider_message(provider)
        ],
        sent=update_event.sent_at_as_cap_datetime_string,
        expires=update_event.transmitted_finishes_at_as_cap_datetime_string,
        channel="test"
    )


@pytest.mark.parametrize('provider,provider_capitalised', [
    ['ee', 'EE'],
    ['three', 'Three'],
    ['o2', 'O2'],
    ['vodafone', 'Vodafone'],
])
def test_send_broadcast_provider_message_sends_cancel_with_references(
    mocker, sample_service, provider, provider_capitalised
):
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

    create_broadcast_provider_message(alert_event, provider)
    create_broadcast_provider_message(update_event, provider)

    mock_cancel_broadcast = mocker.patch(
        f'app.clients.cbc_proxy.CBCProxy{provider_capitalised}.cancel_broadcast',
    )

    send_broadcast_provider_message(provider=provider, broadcast_event_id=str(cancel_event.id))

    broadcast_provider_message = cancel_event.get_provider_message(provider)
    assert broadcast_provider_message.status == BroadcastProviderMessageStatus.SENDING

    mock_cancel_broadcast.assert_called_once_with(
        identifier=str(broadcast_provider_message.id),
        message_number=mocker.ANY,
        previous_provider_messages=[
            alert_event.get_provider_message(provider),
            update_event.get_provider_message(provider)
        ],
        sent=cancel_event.sent_at_as_cap_datetime_string,
    )


@pytest.mark.parametrize("provider,provider_capitalised", [
    ['ee', 'EE'],
    ['three', 'Three'],
    ['o2', 'O2'],
    ['vodafone', 'Vodafone'],
])
def test_send_broadcast_provider_message_errors(mocker, sample_service, provider, provider_capitalised):
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
        f'app.clients.cbc_proxy.CBCProxy{provider_capitalised}.create_and_send_broadcast',
        side_effect=CBCProxyRetryableException('oh no'),
    )
    mock_retry = mocker.patch('app.celery.broadcast_message_tasks.send_broadcast_provider_message.retry')

    send_broadcast_provider_message(provider=provider, broadcast_event_id=str(event.id))

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
        channel="test"
    )
    mock_retry.assert_called_once_with(
        countdown=1,
        exc=mock_create_broadcast.side_effect,
        queue='broadcast-tasks'
    )


@pytest.mark.parametrize('num_retries, expected_countdown', [
    (0, 1),
    (5, 32),
    (20, 300),
])
def test_send_broadcast_provider_message_delays_retry_exponentially(
    mocker,
    sample_service,
    num_retries,
    expected_countdown
):
    template = create_template(sample_service, BROADCAST_TYPE)

    broadcast_message = create_broadcast_message(template,  status=BroadcastStatusType.BROADCASTING)
    event = create_broadcast_event(broadcast_message)

    mock_create_broadcast = mocker.patch(
        'app.clients.cbc_proxy.CBCProxyEE.create_and_send_broadcast',
        side_effect=CBCProxyRetryableException('oh no'),
    )
    mock_retry = mocker.patch('app.celery.broadcast_message_tasks.send_broadcast_provider_message.retry')

    # patch celery request context as shown here: https://stackoverflow.com/a/59870468
    mock_celery_task_request_context = mocker.patch("celery.app.task.Task.request")
    mock_celery_task_request_context.retries = num_retries

    send_broadcast_provider_message(provider='ee', broadcast_event_id=str(event.id))

    mock_create_broadcast.assert_called_once_with(
        identifier=ANY,
        message_number=mocker.ANY,
        headline="GOV.UK Notify Broadcast",
        description='this is an emergency broadcast message',
        areas=[],
        sent=event.sent_at_as_cap_datetime_string,
        expires=event.transmitted_finishes_at_as_cap_datetime_string,
        channel='test',
    )
    mock_retry.assert_called_once_with(
        countdown=expected_countdown,
        exc=mock_create_broadcast.side_effect,
        queue='broadcast-tasks'
    )


@pytest.mark.parametrize("provider,provider_capitalised", [
    ['ee', 'EE'],
    ['three', 'Three'],
    ['o2', 'O2'],
    ['vodafone', 'Vodafone'],
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


@pytest.mark.parametrize('retry_count, expected_delay', [
    (0, 1),
    (1, 2),
    (2, 4),
    (8, 256),
    (9, 300),
    (10, 300),
    (1000, 300),
])
def test_get_retry_delay_has_capped_backoff(retry_count, expected_delay):
    assert get_retry_delay(retry_count) == expected_delay


@freeze_time('2021-01-01 12:00')
def test_check_provider_message_should_retry_doesnt_raise_if_event_hasnt_expired_yet(sample_template):
    broadcast_message = create_broadcast_message(sample_template)
    current_event = create_broadcast_event(
        broadcast_message,
        transmitted_starts_at=datetime(2021, 1, 1, 0, 0),
        transmitted_finishes_at=datetime(2021, 1, 1, 12, 1),
    )
    provider_message = create_broadcast_provider_message(current_event, 'ee')

    check_provider_message_should_retry(provider_message)


@freeze_time('2021-01-01 12:00')
def test_check_provider_message_should_retry_raises_if_event_has_expired(sample_template):
    broadcast_message = create_broadcast_message(sample_template)
    current_event = create_broadcast_event(
        broadcast_message,
        transmitted_starts_at=datetime(2021, 1, 1, 0, 0),
        transmitted_finishes_at=datetime(2021, 1, 1, 11, 59),
    )
    provider_message = create_broadcast_provider_message(current_event, 'ee')

    with pytest.raises(MaxRetriesExceededError) as exc:
        check_provider_message_should_retry(provider_message)
    assert 'The expiry time of 2021-01-01 11:59:00 has already passed' in str(exc.value)


@freeze_time('2021-01-01 12:00')
def test_check_provider_message_should_retry_raises_if_a_newer_event_exists(sample_template):
    broadcast_message = create_broadcast_message(sample_template)
    # event approved at midnight
    past_event = create_broadcast_event(
        broadcast_message,
        message_type='alert',
        sent_at=datetime(2021, 1, 1, 0, 0),
        transmitted_starts_at=datetime(2021, 1, 1, 0, 0),
        transmitted_finishes_at=datetime(2021, 1, 2, 0, 0),
    )
    # event updated at 5am (this is the event we're currently trying to send)
    current_event = create_broadcast_event(
        broadcast_message,
        message_type='update',
        sent_at=datetime(2021, 1, 1, 5, 0),
        transmitted_starts_at=datetime(2021, 1, 1, 0, 0),
        transmitted_finishes_at=datetime(2021, 1, 2, 0, 0),
    )
    # event updated at 7am
    future_event = create_broadcast_event(
        broadcast_message,
        message_type='update',
        sent_at=datetime(2021, 1, 1, 7, 0),
        transmitted_starts_at=datetime(2021, 1, 1, 0, 0),
        transmitted_finishes_at=datetime(2021, 1, 2, 0, 0),
    )
    # event cancelled at 10am
    futurest_event = create_broadcast_event(
        broadcast_message,
        message_type='cancel',
        sent_at=datetime(2021, 1, 1, 10, 0),
        transmitted_starts_at=datetime(2021, 1, 1, 0, 0),
        transmitted_finishes_at=datetime(2021, 1, 2, 0, 0),
    )

    provider_message = create_broadcast_provider_message(current_event, 'ee')

    # even though the task is going on until midnight tomorrow, we shouldn't send the update now, because the cancel
    # message will be in the pipeline somewhere.
    with pytest.raises(MaxRetriesExceededError) as exc:
        check_provider_message_should_retry(provider_message)

    assert f'This event has been superceeded by cancel broadcast_event {futurest_event.id}' in str(exc.value)
