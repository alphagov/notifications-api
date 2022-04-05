import pytest

from app.broadcast_message.utils import (
    _create_p1_zendesk_alert,
    update_broadcast_message_status,
)
from app.errors import InvalidRequest
from app.models import (
    BROADCAST_TYPE,
    BroadcastEventMessageType,
    BroadcastStatusType,
)
from tests.app.db import (
    create_api_key,
    create_broadcast_message,
    create_template,
    create_user,
)
from tests.conftest import set_config


def test_update_broadcast_message_status_stores_approved_by_and_approved_at_and_queues_task(
    sample_broadcast_service,
    mocker
):
    template = create_template(sample_broadcast_service, BROADCAST_TYPE, content='emergency broadcast')
    broadcast_message = create_broadcast_message(
        template,
        status=BroadcastStatusType.PENDING_APPROVAL,
        areas={
            "ids": ["london"],
            "simple_polygons": [[[51.30, 0.7], [51.28, 0.8], [51.25, -0.7]]]
        }
    )
    approver = create_user(email='approver@gov.uk')
    sample_broadcast_service.users.append(approver)
    mock_task = mocker.patch('app.celery.broadcast_message_tasks.send_broadcast_event.apply_async')

    update_broadcast_message_status(
        broadcast_message, BroadcastStatusType.BROADCASTING, approver
    )

    assert broadcast_message.status == BroadcastStatusType.BROADCASTING
    assert broadcast_message.approved_at is not None
    assert broadcast_message.approved_by_id == approver.id

    assert len(broadcast_message.events) == 1
    alert_event = broadcast_message.events[0]

    mock_task.assert_called_once_with(kwargs={'broadcast_event_id': str(alert_event.id)}, queue='broadcast-tasks')

    assert alert_event.service_id == sample_broadcast_service.id
    assert alert_event.transmitted_areas == broadcast_message.areas
    assert alert_event.message_type == BroadcastEventMessageType.ALERT
    assert alert_event.transmitted_finishes_at == broadcast_message.finishes_at
    assert alert_event.transmitted_content == {"body": "emergency broadcast"}


def test_update_broadcast_message_status_for_cancelling_broadcast_from_admin_interface(
    sample_broadcast_service,
    mocker,
):
    template = create_template(sample_broadcast_service, BROADCAST_TYPE, content='emergency broadcast')
    broadcast_message = create_broadcast_message(
        template,
        status=BroadcastStatusType.BROADCASTING,
        areas={
            "ids": ["london"],
            "simple_polygons": [[[51.30, 0.7], [51.28, 0.8], [51.25, -0.7]]]
        }
    )
    canceller = sample_broadcast_service.created_by

    mock_task = mocker.patch('app.celery.broadcast_message_tasks.send_broadcast_event.apply_async')

    update_broadcast_message_status(
        broadcast_message, BroadcastStatusType.CANCELLED, updating_user=canceller, api_key_id=None
    )

    assert broadcast_message.status == BroadcastStatusType.CANCELLED
    assert broadcast_message.cancelled_at is not None
    assert broadcast_message.cancelled_by_id == canceller.id
    assert broadcast_message.cancelled_by_api_key_id is None

    assert len(broadcast_message.events) == 1
    alert_event = broadcast_message.events[0]

    mock_task.assert_called_once_with(kwargs={'broadcast_event_id': str(alert_event.id)}, queue='broadcast-tasks')

    assert alert_event.service_id == sample_broadcast_service.id
    assert alert_event.message_type == BroadcastEventMessageType.CANCEL


def test_update_broadcast_message_status_for_cancelling_broadcast_from_API_call(
    sample_broadcast_service,
    mocker,
):
    api_key = create_api_key(service=sample_broadcast_service)
    template = create_template(sample_broadcast_service, BROADCAST_TYPE, content='emergency broadcast')
    broadcast_message = create_broadcast_message(
        template,
        status=BroadcastStatusType.BROADCASTING,
        areas={
            "ids": ["london"],
            "simple_polygons": [[[51.30, 0.7], [51.28, 0.8], [51.25, -0.7]]]
        }
    )
    mock_task = mocker.patch('app.celery.broadcast_message_tasks.send_broadcast_event.apply_async')

    update_broadcast_message_status(
        broadcast_message, BroadcastStatusType.CANCELLED, updating_user=None, api_key_id=api_key.id
    )

    assert broadcast_message.status == BroadcastStatusType.CANCELLED
    assert broadcast_message.cancelled_at is not None
    assert broadcast_message.cancelled_by_id is None
    assert broadcast_message.cancelled_by_api_key_id == api_key.id

    assert len(broadcast_message.events) == 1
    alert_event = broadcast_message.events[0]

    mock_task.assert_called_once_with(kwargs={'broadcast_event_id': str(alert_event.id)}, queue='broadcast-tasks')

    assert alert_event.service_id == sample_broadcast_service.id
    assert alert_event.message_type == BroadcastEventMessageType.CANCEL


def test_update_broadcast_message_status_for_rejecting_broadcast_via_admin_interface(
    sample_broadcast_service,
    mocker
):
    template = create_template(sample_broadcast_service, BROADCAST_TYPE, content='emergency broadcast')
    broadcast_message = create_broadcast_message(
        template,
        status=BroadcastStatusType.PENDING_APPROVAL,
        areas={
            "ids": ["london"],
            "simple_polygons": [[[51.30, 0.7], [51.28, 0.8], [51.25, -0.7]]]
        }
    )
    mock_task = mocker.patch('app.celery.broadcast_message_tasks.send_broadcast_event.apply_async')

    update_broadcast_message_status(
        broadcast_message, BroadcastStatusType.REJECTED, updating_user=sample_broadcast_service.created_by
    )

    assert broadcast_message.status == BroadcastStatusType.REJECTED
    assert broadcast_message.cancelled_at is None
    assert broadcast_message.cancelled_by_id is None
    assert broadcast_message.updated_at is not None

    assert not mock_task.called
    assert len(broadcast_message.events) == 0


def test_update_broadcast_message_status_for_rejecting_broadcast_from_API_call(
    sample_broadcast_service,
    mocker
):
    api_key = create_api_key(service=sample_broadcast_service)
    template = create_template(sample_broadcast_service, BROADCAST_TYPE, content='emergency broadcast')
    broadcast_message = create_broadcast_message(
        template,
        status=BroadcastStatusType.PENDING_APPROVAL,
        areas={
            "ids": ["london"],
            "simple_polygons": [[[51.30, 0.7], [51.28, 0.8], [51.25, -0.7]]]
        }
    )
    mock_task = mocker.patch('app.celery.broadcast_message_tasks.send_broadcast_event.apply_async')

    update_broadcast_message_status(
        broadcast_message, BroadcastStatusType.REJECTED, api_key_id=api_key.id
    )

    assert broadcast_message.status == BroadcastStatusType.REJECTED
    assert broadcast_message.cancelled_at is None
    assert broadcast_message.cancelled_by_id is None
    assert broadcast_message.cancelled_by_api_key_id is None
    assert broadcast_message.updated_at is not None

    assert not mock_task.called
    assert len(broadcast_message.events) == 0


@pytest.mark.parametrize('current_status, new_status', [
    (BroadcastStatusType.DRAFT, BroadcastStatusType.DRAFT),
    (BroadcastStatusType.DRAFT, BroadcastStatusType.BROADCASTING),
    (BroadcastStatusType.DRAFT, BroadcastStatusType.CANCELLED),

    (BroadcastStatusType.PENDING_APPROVAL, BroadcastStatusType.PENDING_APPROVAL),
    (BroadcastStatusType.PENDING_APPROVAL, BroadcastStatusType.CANCELLED),
    (BroadcastStatusType.PENDING_APPROVAL, BroadcastStatusType.COMPLETED),

    (BroadcastStatusType.REJECTED, BroadcastStatusType.REJECTED),
    (BroadcastStatusType.REJECTED, BroadcastStatusType.BROADCASTING),
    (BroadcastStatusType.REJECTED, BroadcastStatusType.CANCELLED),
    (BroadcastStatusType.REJECTED, BroadcastStatusType.COMPLETED),

    (BroadcastStatusType.BROADCASTING, BroadcastStatusType.DRAFT),
    (BroadcastStatusType.BROADCASTING, BroadcastStatusType.PENDING_APPROVAL),
    (BroadcastStatusType.BROADCASTING, BroadcastStatusType.BROADCASTING),

    (BroadcastStatusType.COMPLETED, BroadcastStatusType.DRAFT),
    (BroadcastStatusType.COMPLETED, BroadcastStatusType.PENDING_APPROVAL),
    (BroadcastStatusType.COMPLETED, BroadcastStatusType.BROADCASTING),
    (BroadcastStatusType.COMPLETED, BroadcastStatusType.CANCELLED),

    (BroadcastStatusType.CANCELLED, BroadcastStatusType.DRAFT),
    (BroadcastStatusType.CANCELLED, BroadcastStatusType.PENDING_APPROVAL),
    (BroadcastStatusType.CANCELLED, BroadcastStatusType.BROADCASTING),
    (BroadcastStatusType.CANCELLED, BroadcastStatusType.COMPLETED),
])
def test_update_broadcast_message_status_restricts_status_transitions_to_explicit_list(
    sample_broadcast_service,
    mocker,
    current_status,
    new_status
):
    t = create_template(sample_broadcast_service, BROADCAST_TYPE)
    broadcast_message = create_broadcast_message(t, status=current_status)
    approver = create_user(email='approver@gov.uk')
    sample_broadcast_service.users.append(approver)
    mock_task = mocker.patch('app.celery.broadcast_message_tasks.send_broadcast_event.apply_async')

    with pytest.raises(expected_exception=InvalidRequest) as e:
        update_broadcast_message_status(broadcast_message, new_status, approver)

    assert mock_task.called is False
    assert f'from {current_status} to {new_status}' in str(e.value)


@pytest.mark.parametrize('is_platform_admin', [True, False])
def test_update_broadcast_message_status_rejects_approval_from_creator(
    sample_broadcast_service,
    mocker,
    is_platform_admin
):
    template = create_template(sample_broadcast_service, BROADCAST_TYPE)
    broadcast_message = create_broadcast_message(template, status=BroadcastStatusType.PENDING_APPROVAL)
    creator_and_approver = sample_broadcast_service.created_by
    creator_and_approver.platform_admin = is_platform_admin
    mock_task = mocker.patch('app.celery.broadcast_message_tasks.send_broadcast_event.apply_async')

    with pytest.raises(expected_exception=InvalidRequest) as e:
        update_broadcast_message_status(
            broadcast_message, BroadcastStatusType.BROADCASTING, creator_and_approver
        )

    assert mock_task.called is False
    assert 'cannot approve their own broadcast' in str(e.value)


def test_update_broadcast_message_status_rejects_approval_of_broadcast_with_no_areas(
    admin_request,
    sample_broadcast_service,
    mocker
):
    template = create_template(sample_broadcast_service, BROADCAST_TYPE)
    broadcast = create_broadcast_message(template, status=BroadcastStatusType.PENDING_APPROVAL)
    approver = create_user(email='approver@gov.uk')
    sample_broadcast_service.users.append(approver)
    mock_task = mocker.patch('app.celery.broadcast_message_tasks.send_broadcast_event.apply_async')

    with pytest.raises(expected_exception=InvalidRequest) as e:
        update_broadcast_message_status(broadcast, BroadcastStatusType.BROADCASTING, approver)

    assert mock_task.called is False
    assert f'broadcast_message {broadcast.id} has no selected areas and so cannot be broadcasted.' in str(e.value)


def test_update_broadcast_message_status_allows_trial_mode_services_to_approve_own_message(
    notify_db,
    sample_broadcast_service,
    mocker
):
    sample_broadcast_service.restricted = True
    template = create_template(sample_broadcast_service, BROADCAST_TYPE)
    broadcast_message = create_broadcast_message(
        template,
        status=BroadcastStatusType.PENDING_APPROVAL,
        areas={"ids": ["london"], "simple_polygons": [[[51.30, 0.7], [51.28, 0.8], [51.25, -0.7]]]}
    )
    creator_and_approver = sample_broadcast_service.created_by
    mock_task = mocker.patch('app.celery.broadcast_message_tasks.send_broadcast_event.apply_async')

    update_broadcast_message_status(
        broadcast_message, BroadcastStatusType.BROADCASTING, creator_and_approver
    )

    assert broadcast_message.status == BroadcastStatusType.BROADCASTING
    assert broadcast_message.approved_at is not None
    assert broadcast_message.created_by_id == template.created_by_id
    assert broadcast_message.approved_by_id == template.created_by_id
    assert not mock_task.called


@pytest.mark.parametrize('broadcast_message_stubbed, service_restricted_before_approval', [
    (True, True),
    (True, False),
    (False, True),
])
def test_update_broadcast_message_status_when_broadcast_message_is_stubbed_or_service_not_live(
    admin_request,
    sample_broadcast_service,
    mocker,
    broadcast_message_stubbed,
    service_restricted_before_approval,
):
    sample_broadcast_service.restricted = broadcast_message_stubbed
    template = create_template(sample_broadcast_service, BROADCAST_TYPE, content='emergency broadcast')
    broadcast_message = create_broadcast_message(
        template,
        status=BroadcastStatusType.PENDING_APPROVAL,
        areas={"ids": ["london"], "simple_polygons": [[[51.30, 0.7], [51.28, 0.8], [51.25, -0.7]]]},
        stubbed=broadcast_message_stubbed
    )
    approver = create_user(email='approver@gov.uk')
    sample_broadcast_service.users.append(approver)
    mock_task = mocker.patch('app.celery.broadcast_message_tasks.send_broadcast_event.apply_async')

    sample_broadcast_service.restricted = service_restricted_before_approval

    update_broadcast_message_status(
        broadcast_message, BroadcastStatusType.BROADCASTING, approver
    )
    assert broadcast_message.status == BroadcastStatusType.BROADCASTING
    assert broadcast_message.approved_at is not None
    assert broadcast_message.approved_by_id == approver.id

    # The broadcast can be approved, but does not create a broadcast_event in the database or put a task on the queue
    assert len(broadcast_message.events) == 0
    assert len(mock_task.mock_calls) == 0


def test_update_broadcast_message_status_creates_event_with_correct_content_if_broadcast_has_no_template(
    admin_request,
    sample_broadcast_service,
    mocker
):
    broadcast_message = create_broadcast_message(
        service=sample_broadcast_service,
        template=None,
        content='tailor made emergency broadcast content',
        status=BroadcastStatusType.PENDING_APPROVAL,
        areas={
            "ids": ["london"],
            "simple_polygons": [[[51.30, 0.7], [51.28, 0.8], [51.25, -0.7]]]
        }
    )
    approver = create_user(email='approver@gov.uk')
    sample_broadcast_service.users.append(approver)
    mock_task = mocker.patch('app.celery.broadcast_message_tasks.send_broadcast_event.apply_async')

    update_broadcast_message_status(
        broadcast_message, BroadcastStatusType.BROADCASTING, approver
    )

    assert broadcast_message.status == BroadcastStatusType.BROADCASTING

    assert len(broadcast_message.events) == 1
    alert_event = broadcast_message.events[0]

    mock_task.assert_called_once_with(kwargs={'broadcast_event_id': str(alert_event.id)}, queue='broadcast-tasks')

    assert alert_event.transmitted_content == {"body": "tailor made emergency broadcast content"}


def test_update_broadcast_message_status_creates_zendesk_ticket(
    mocker,
    notify_api,
    sample_broadcast_service
):
    broadcast_message = create_broadcast_message(
        service=sample_broadcast_service,
        content='tailor made emergency broadcast content',
        status=BroadcastStatusType.PENDING_APPROVAL,
        areas={"names": ["England", "Scotland"], "simple_polygons": ['polygons']}
    )
    approver = create_user(email='approver@gov.uk')
    sample_broadcast_service.users.append(approver)

    mocker.patch('app.celery.broadcast_message_tasks.send_broadcast_event.apply_async')
    mock_send_ticket_to_zendesk = mocker.patch(
        'app.broadcast_message.utils.zendesk_client.send_ticket_to_zendesk',
        autospec=True,
    )

    with set_config(notify_api, 'NOTIFY_ENVIRONMENT', 'live'):
        update_broadcast_message_status(
            broadcast_message, BroadcastStatusType.BROADCASTING, approver
        )

    mock_send_ticket_to_zendesk.assert_called_once()


def test_create_p1_zendesk_alert(sample_broadcast_service, mocker, notify_api):
    broadcast_message = create_broadcast_message(
        service=sample_broadcast_service,
        content='tailor made emergency broadcast content',
        status=BroadcastStatusType.BROADCASTING,
        areas={"names": ["England", "Scotland"]}
    )

    mock_send_ticket_to_zendesk = mocker.patch(
        'app.broadcast_message.utils.zendesk_client.send_ticket_to_zendesk',
        autospec=True,
    )

    with set_config(notify_api, 'NOTIFY_ENVIRONMENT', 'live'):
        _create_p1_zendesk_alert(broadcast_message)

    ticket = mock_send_ticket_to_zendesk.call_args_list[0].args[0]
    assert ticket.subject == 'Live broadcast sent'
    assert ticket.ticket_type == 'incident'
    assert str(broadcast_message.id) in ticket.message
    assert 'channel severe' in ticket.message
    assert "areas ['England', 'Scotland']" in ticket.message
    assert "tailor made emergency" in ticket.message


def test_create_p1_zendesk_alert_doesnt_alert_when_cancelling(mocker, notify_api, sample_broadcast_service):
    broadcast_message = create_broadcast_message(
        service=sample_broadcast_service,
        content='tailor made emergency broadcast content',
        status=BroadcastStatusType.CANCELLED,
        areas={"names": ["England", "Scotland"]}
    )

    mock_send_ticket_to_zendesk = mocker.patch(
        'app.broadcast_message.utils.zendesk_client.send_ticket_to_zendesk',
        autospec=True,
    )

    with set_config(notify_api, 'NOTIFY_ENVIRONMENT', 'live'):
        _create_p1_zendesk_alert(broadcast_message)

    mock_send_ticket_to_zendesk.assert_not_called()


def test_create_p1_zendesk_alert_doesnt_alert_on_staging(mocker, notify_api, sample_broadcast_service):
    broadcast_message = create_broadcast_message(
        service=sample_broadcast_service,
        content='tailor made emergency broadcast content',
        status=BroadcastStatusType.BROADCASTING,
        areas={"names": ["England", "Scotland"]}
    )

    mock_send_ticket_to_zendesk = mocker.patch(
        'app.broadcast_message.utils.zendesk_client.send_ticket_to_zendesk',
        autospec=True,
    )

    with set_config(notify_api, 'NOTIFY_ENVIRONMENT', 'staging'):
        _create_p1_zendesk_alert(broadcast_message)

    mock_send_ticket_to_zendesk.assert_not_called()
