from unittest.mock import ANY
import uuid

from freezegun import freeze_time
import pytest

from app.models import BROADCAST_TYPE, BroadcastStatusType, BroadcastEventMessageType

from tests.app.db import create_broadcast_message, create_template, create_service, create_user


def test_get_broadcast_message(admin_request, sample_broadcast_service):
    t = create_template(
        sample_broadcast_service,
        BROADCAST_TYPE,
        content='This is a ((thing))'
    )
    bm = create_broadcast_message(
        t,
        areas={
            "areas": ['place A', 'region B'],
            "simple_polygons": [[[50.1, 1.2], [50.12, 1.2], [50.13, 1.2]]],
        },
        personalisation={
            'thing': 'test',
        },
    )

    response = admin_request.get(
        'broadcast_message.get_broadcast_message',
        service_id=t.service_id,
        broadcast_message_id=bm.id,
        _expected_status=200
    )

    assert response['id'] == str(bm.id)
    assert response['template_id'] == str(t.id)
    assert response['template_content'] == 'This is a test'
    assert response['template_name'] == t.name
    assert response['status'] == BroadcastStatusType.DRAFT
    assert response['created_at'] is not None
    assert response['starts_at'] is None
    assert response['areas'] == ['place A', 'region B']
    assert response['personalisation'] == {'thing': 'test'}


def test_get_broadcast_message_404s_if_message_doesnt_exist(admin_request, sample_broadcast_service):
    err = admin_request.get(
        'broadcast_message.get_broadcast_message',
        service_id=sample_broadcast_service.id,
        broadcast_message_id=uuid.uuid4(),
        _expected_status=404
    )
    assert err == {'message': 'No result found', 'result': 'error'}


def test_get_broadcast_message_404s_if_message_is_for_different_service(admin_request, sample_broadcast_service):
    other_service = create_service(service_name='other')
    other_template = create_template(other_service, BROADCAST_TYPE)
    bm = create_broadcast_message(other_template)

    err = admin_request.get(
        'broadcast_message.get_broadcast_message',
        service_id=sample_broadcast_service.id,
        broadcast_message_id=bm.id,
        _expected_status=404
    )
    assert err == {'message': 'No result found', 'result': 'error'}


@freeze_time('2020-01-01')
def test_get_broadcast_messages_for_service(admin_request, sample_broadcast_service):
    t = create_template(sample_broadcast_service, BROADCAST_TYPE)

    with freeze_time('2020-01-01 12:00'):
        bm1 = create_broadcast_message(t, personalisation={'foo': 'bar'})
    with freeze_time('2020-01-01 13:00'):
        bm2 = create_broadcast_message(t, personalisation={'foo': 'baz'})

    response = admin_request.get(
        'broadcast_message.get_broadcast_messages_for_service',
        service_id=t.service_id,
        _expected_status=200
    )

    assert response['broadcast_messages'][0]['id'] == str(bm1.id)
    assert response['broadcast_messages'][1]['id'] == str(bm2.id)


@freeze_time('2020-01-01')
def test_create_broadcast_message(admin_request, sample_broadcast_service):
    t = create_template(sample_broadcast_service, BROADCAST_TYPE)

    response = admin_request.post(
        'broadcast_message.create_broadcast_message',
        _data={
            'template_id': str(t.id),
            'service_id': str(t.service_id),
            'created_by': str(t.created_by_id),
        },
        service_id=t.service_id,
        _expected_status=201
    )

    assert response['template_name'] == t.name
    assert response['status'] == BroadcastStatusType.DRAFT
    assert response['created_at'] is not None
    assert response['created_by_id'] == str(t.created_by_id)
    assert response['personalisation'] == {}
    assert response['areas'] == []


@pytest.mark.parametrize('data, expected_errors', [
    (
        {},
        [
            {'error': 'ValidationError', 'message': 'template_id is a required property'},
            {'error': 'ValidationError', 'message': 'service_id is a required property'},
            {'error': 'ValidationError', 'message': 'created_by is a required property'}
        ]
    ),
    (
        {
            'template_id': str(uuid.uuid4()),
            'service_id': str(uuid.uuid4()),
            'created_by': str(uuid.uuid4()),
            'foo': 'something else'
        },
        [
            {'error': 'ValidationError', 'message': 'Additional properties are not allowed (foo was unexpected)'}
        ]
    )
])
def test_create_broadcast_message_400s_if_json_schema_fails_validation(
    admin_request,
    sample_broadcast_service,
    data,
    expected_errors
):
    t = create_template(sample_broadcast_service, BROADCAST_TYPE)

    response = admin_request.post(
        'broadcast_message.create_broadcast_message',
        _data=data,
        service_id=t.service_id,
        _expected_status=400
    )
    assert response['errors'] == expected_errors


@pytest.mark.parametrize('status', [
    BroadcastStatusType.DRAFT,
    BroadcastStatusType.PENDING_APPROVAL,
    BroadcastStatusType.REJECTED,
])
def test_update_broadcast_message_allows_edit_while_not_yet_live(admin_request, sample_broadcast_service, status):
    t = create_template(sample_broadcast_service, BROADCAST_TYPE)
    bm = create_broadcast_message(
        t,
        areas={"areas": ['manchester'], "simple_polygons": [[[50.12, 1.2], [50.13, 1.2], [50.14, 1.21]]]},
        status=status
    )

    response = admin_request.post(
        'broadcast_message.update_broadcast_message',
        _data={
            'starts_at': '2020-06-01 20:00:01',
            'areas': ['london', 'glasgow'],
            "simple_polygons": [[[51.12, 0.2], [50.13, 0.4], [50.14, 0.45]]]
        },
        service_id=t.service_id,
        broadcast_message_id=bm.id,
        _expected_status=200
    )

    assert response['starts_at'] == '2020-06-01T20:00:01.000000Z'
    assert response['areas'] == ['london', 'glasgow']
    assert response['simple_polygons'] == [[[51.12, 0.2], [50.13, 0.4], [50.14, 0.45]]]
    assert response['updated_at'] is not None


@pytest.mark.parametrize('status', [
    BroadcastStatusType.BROADCASTING,
    BroadcastStatusType.CANCELLED,
    BroadcastStatusType.COMPLETED,
    BroadcastStatusType.TECHNICAL_FAILURE,
])
def test_update_broadcast_message_doesnt_allow_edits_after_broadcast_goes_live(
    admin_request, sample_broadcast_service, status
):
    t = create_template(sample_broadcast_service, BROADCAST_TYPE)
    bm = create_broadcast_message(t, areas=['manchester'], status=status)

    response = admin_request.post(
        'broadcast_message.update_broadcast_message',
        _data={'areas': ['london', 'glasgow']},
        service_id=t.service_id,
        broadcast_message_id=bm.id,
        _expected_status=400
    )
    assert f'status {status}' in response['message']


def test_update_broadcast_message_sets_finishes_at_separately(admin_request, sample_broadcast_service):
    t = create_template(sample_broadcast_service, BROADCAST_TYPE)
    bm = create_broadcast_message(
        t,
        areas={"areas": ['london'], "simple_polygons": [[[50.12, 1.2], [50.13, 1.2], [50.14, 1.21]]]}
    )

    response = admin_request.post(
        'broadcast_message.update_broadcast_message',
        _data={'starts_at': '2020-06-01 20:00:01', 'finishes_at': '2020-06-02 20:00:01'},
        service_id=t.service_id,
        broadcast_message_id=bm.id,
        _expected_status=200
    )

    assert response['starts_at'] == '2020-06-01T20:00:01.000000Z'
    assert response['finishes_at'] == '2020-06-02T20:00:01.000000Z'
    assert response['updated_at'] is not None


@pytest.mark.parametrize('input_dt', [
    '2020-06-01 20:00:01',
    '2020-06-01T20:00:01',
    '2020-06-01 20:00:01Z',
    '2020-06-01T20:00:01+00:00',
])
def test_update_broadcast_message_allows_sensible_datetime_formats(admin_request, sample_broadcast_service, input_dt):
    t = create_template(sample_broadcast_service, BROADCAST_TYPE)
    bm = create_broadcast_message(t)

    response = admin_request.post(
        'broadcast_message.update_broadcast_message',
        _data={'starts_at': input_dt},
        service_id=t.service_id,
        broadcast_message_id=bm.id,
        _expected_status=200
    )

    assert response['starts_at'] == '2020-06-01T20:00:01.000000Z'
    assert response['updated_at'] is not None


def test_update_broadcast_message_doesnt_let_you_update_status(admin_request, sample_broadcast_service):
    t = create_template(sample_broadcast_service, BROADCAST_TYPE)
    bm = create_broadcast_message(t)

    response = admin_request.post(
        'broadcast_message.update_broadcast_message',
        _data={
            'areas': ['glasgow'],
            "simple_polygons": [[[55.86, -4.25], [55.85, -4.25], [55.87, -4.24]]],
            'status': BroadcastStatusType.BROADCASTING},
        service_id=t.service_id,
        broadcast_message_id=bm.id,
        _expected_status=400
    )

    assert response['errors'] == [{
        'error': 'ValidationError',
        'message': 'Additional properties are not allowed (status was unexpected)'
    }]


@pytest.mark.parametrize("incomplete_area_data", [
    {"areas": ["cardiff"]},
    {"simple_polygons": [[[51.28, -3.11], [51.29, -3.12], [51.27, -3.10]]]},
])
def test_update_broadcast_message_doesnt_let_you_update_areas_but_not_polygons(
    admin_request, sample_broadcast_service, incomplete_area_data
):
    template = create_template(sample_broadcast_service, BROADCAST_TYPE)
    broadcast_message = create_broadcast_message(template)

    response = admin_request.post(
        'broadcast_message.update_broadcast_message',
        _data=incomplete_area_data,
        service_id=template.service_id,
        broadcast_message_id=broadcast_message.id,
        _expected_status=400
    )

    assert response[
        'message'
    ] == f'Cannot update broadcast_message {broadcast_message.id}, areas or polygons are missing.'


def test_update_broadcast_message_status(admin_request, sample_broadcast_service):
    t = create_template(sample_broadcast_service, BROADCAST_TYPE)
    bm = create_broadcast_message(t, status=BroadcastStatusType.DRAFT)

    response = admin_request.post(
        'broadcast_message.update_broadcast_message_status',
        _data={'status': BroadcastStatusType.PENDING_APPROVAL, 'created_by': str(t.created_by_id)},
        service_id=t.service_id,
        broadcast_message_id=bm.id,
        _expected_status=200
    )

    assert response['status'] == BroadcastStatusType.PENDING_APPROVAL
    assert response['updated_at'] is not None


def test_update_broadcast_message_status_doesnt_let_you_update_other_things(admin_request, sample_broadcast_service):
    t = create_template(sample_broadcast_service, BROADCAST_TYPE)
    bm = create_broadcast_message(t)

    response = admin_request.post(
        'broadcast_message.update_broadcast_message_status',
        _data={'areas': ['glasgow'], 'status': BroadcastStatusType.BROADCASTING, 'created_by': str(t.created_by_id)},
        service_id=t.service_id,
        broadcast_message_id=bm.id,
        _expected_status=400
    )

    assert response['errors'] == [{
        'error': 'ValidationError',
        'message': 'Additional properties are not allowed (areas was unexpected)'
    }]


def test_update_broadcast_message_status_stores_cancelled_by_and_cancelled_at(
    admin_request, sample_broadcast_service, mocker
):
    t = create_template(sample_broadcast_service, BROADCAST_TYPE, content='emergency broadcast')
    bm = create_broadcast_message(t, status=BroadcastStatusType.BROADCASTING)
    canceller = create_user(email='canceller@gov.uk')
    sample_broadcast_service.users.append(canceller)
    mock_task = mocker.patch('app.celery.broadcast_message_tasks.send_broadcast_event.apply_async')

    response = admin_request.post(
        'broadcast_message.update_broadcast_message_status',
        _data={'status': BroadcastStatusType.CANCELLED, 'created_by': str(canceller.id)},
        service_id=t.service_id,
        broadcast_message_id=bm.id,
        _expected_status=200
    )

    assert len(bm.events) == 1
    cancel_event = bm.events[0]

    cancel_id = str(cancel_event.id)

    mock_task.assert_called_once_with(kwargs={'broadcast_event_id': cancel_id}, queue='notify-internal-tasks')
    assert response['status'] == BroadcastStatusType.CANCELLED
    assert response['cancelled_at'] is not None
    assert response['cancelled_by_id'] == str(canceller.id)

    assert cancel_event.service_id == sample_broadcast_service.id
    assert cancel_event.transmitted_areas == bm.areas
    assert cancel_event.message_type == BroadcastEventMessageType.CANCEL
    assert cancel_event.transmitted_finishes_at == bm.cancelled_at
    assert cancel_event.transmitted_content == {"body": "emergency broadcast"}


def test_update_broadcast_message_status_stores_approved_by_and_approved_at_and_queues_task(
    admin_request,
    sample_broadcast_service,
    mocker
):
    t = create_template(sample_broadcast_service, BROADCAST_TYPE, content='emergency broadcast')
    bm = create_broadcast_message(
        t,
        status=BroadcastStatusType.PENDING_APPROVAL,
        areas={"areas": ["london"], "simple_polygons": [[[51.30, 0.7], [51.28, 0.8], [51.25, -0.7]]]}
    )
    approver = create_user(email='approver@gov.uk')
    sample_broadcast_service.users.append(approver)
    mock_task = mocker.patch('app.celery.broadcast_message_tasks.send_broadcast_event.apply_async')

    response = admin_request.post(
        'broadcast_message.update_broadcast_message_status',
        _data={'status': BroadcastStatusType.BROADCASTING, 'created_by': str(approver.id)},
        service_id=t.service_id,
        broadcast_message_id=bm.id,
        _expected_status=200
    )

    assert response['status'] == BroadcastStatusType.BROADCASTING
    assert response['approved_at'] is not None
    assert response['approved_by_id'] == str(approver.id)

    assert len(bm.events) == 1
    alert_event = bm.events[0]

    mock_task.assert_called_once_with(kwargs={'broadcast_event_id': str(alert_event.id)}, queue='notify-internal-tasks')

    assert alert_event.service_id == sample_broadcast_service.id
    assert alert_event.transmitted_areas == bm.areas
    assert alert_event.message_type == BroadcastEventMessageType.ALERT
    assert alert_event.transmitted_finishes_at == bm.finishes_at
    assert alert_event.transmitted_content == {"body": "emergency broadcast"}


def test_update_broadcast_message_status_rejects_approval_from_creator(
    admin_request,
    sample_broadcast_service,
    mocker
):
    t = create_template(sample_broadcast_service, BROADCAST_TYPE)
    bm = create_broadcast_message(t, status=BroadcastStatusType.PENDING_APPROVAL)
    mock_task = mocker.patch('app.celery.broadcast_message_tasks.send_broadcast_event.apply_async')

    response = admin_request.post(
        'broadcast_message.update_broadcast_message_status',
        _data={'status': BroadcastStatusType.BROADCASTING, 'created_by': str(t.created_by_id)},
        service_id=t.service_id,
        broadcast_message_id=bm.id,
        _expected_status=400
    )

    assert mock_task.called is False
    assert f'cannot approve their own broadcast' in response['message']


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

    response = admin_request.post(
        'broadcast_message.update_broadcast_message_status',
        _data={'status': BroadcastStatusType.BROADCASTING, 'created_by': str(approver.id)},
        service_id=template.service_id,
        broadcast_message_id=broadcast.id,
        _expected_status=400
    )

    assert mock_task.called is False
    assert response[
        'message'
    ] == f'broadcast_message {broadcast.id} has no selected areas and so cannot be broadcasted.'


def test_update_broadcast_message_status_allows_platform_admin_to_approve_own_message(
    notify_db,
    admin_request,
    sample_broadcast_service,
    mocker
):
    user = sample_broadcast_service.created_by
    user.platform_admin = True
    t = create_template(sample_broadcast_service, BROADCAST_TYPE)
    bm = create_broadcast_message(
        t,
        status=BroadcastStatusType.PENDING_APPROVAL,
        areas={"areas": ["london"], "simple_polygons": [[[51.30, 0.7], [51.28, 0.8], [51.25, -0.7]]]}
    )
    mock_task = mocker.patch('app.celery.broadcast_message_tasks.send_broadcast_event.apply_async')

    response = admin_request.post(
        'broadcast_message.update_broadcast_message_status',
        _data={'status': BroadcastStatusType.BROADCASTING, 'created_by': str(user.id)},
        service_id=t.service_id,
        broadcast_message_id=bm.id,
        _expected_status=200
    )

    assert response['status'] == BroadcastStatusType.BROADCASTING
    assert response['approved_at'] is not None
    assert response['created_by_id'] == str(user.id)
    assert response['approved_by_id'] == str(user.id)
    mock_task.assert_called_once_with(
        kwargs={'broadcast_event_id': str(bm.events[0].id)},
        queue='notify-internal-tasks'
    )


def test_update_broadcast_message_status_allows_trial_mode_services_to_approve_own_message(
    notify_db,
    admin_request,
    sample_broadcast_service,
    mocker
):
    sample_broadcast_service.restricted = True
    t = create_template(sample_broadcast_service, BROADCAST_TYPE)
    bm = create_broadcast_message(
        t,
        status=BroadcastStatusType.PENDING_APPROVAL,
        areas={"areas": ["london"], "simple_polygons": [[[51.30, 0.7], [51.28, 0.8], [51.25, -0.7]]]}
    )
    mock_task = mocker.patch('app.celery.broadcast_message_tasks.send_broadcast_event.apply_async')

    response = admin_request.post(
        'broadcast_message.update_broadcast_message_status',
        _data={'status': BroadcastStatusType.BROADCASTING, 'created_by': str(t.created_by_id)},
        service_id=t.service_id,
        broadcast_message_id=bm.id,
        _expected_status=200
    )

    assert response['status'] == BroadcastStatusType.BROADCASTING
    assert response['approved_at'] is not None
    assert response['created_by_id'] == str(t.created_by_id)
    assert response['approved_by_id'] == str(t.created_by_id)
    mock_task.assert_called_once_with(kwargs={'broadcast_event_id': ANY}, queue='notify-internal-tasks')


def test_update_broadcast_message_status_rejects_approval_from_user_not_on_that_service(
    admin_request,
    sample_broadcast_service,
    mocker
):
    t = create_template(sample_broadcast_service, BROADCAST_TYPE)
    bm = create_broadcast_message(t, status=BroadcastStatusType.PENDING_APPROVAL)
    approver = create_user(email='approver@gov.uk')
    mock_task = mocker.patch('app.celery.broadcast_message_tasks.send_broadcast_event.apply_async')

    response = admin_request.post(
        'broadcast_message.update_broadcast_message_status',
        _data={'status': BroadcastStatusType.BROADCASTING, 'created_by': str(approver.id)},
        service_id=t.service_id,
        broadcast_message_id=bm.id,
        _expected_status=400
    )

    assert mock_task.called is False
    assert f'cannot approve broadcast' in response['message']


@pytest.mark.parametrize('current_status, new_status', [
    (BroadcastStatusType.DRAFT, BroadcastStatusType.DRAFT),
    (BroadcastStatusType.BROADCASTING, BroadcastStatusType.PENDING_APPROVAL),
    (BroadcastStatusType.COMPLETED, BroadcastStatusType.BROADCASTING),
    (BroadcastStatusType.CANCELLED, BroadcastStatusType.DRAFT),
    pytest.param(BroadcastStatusType.DRAFT, BroadcastStatusType.BROADCASTING, marks=pytest.mark.xfail()),
])
def test_update_broadcast_message_status_restricts_status_transitions_to_explicit_list(
    admin_request,
    sample_broadcast_service,
    mocker,
    current_status,
    new_status
):
    t = create_template(sample_broadcast_service, BROADCAST_TYPE)
    bm = create_broadcast_message(t, status=current_status)
    approver = create_user(email='approver@gov.uk')
    sample_broadcast_service.users.append(approver)
    mock_task = mocker.patch('app.celery.broadcast_message_tasks.send_broadcast_event.apply_async')

    response = admin_request.post(
        'broadcast_message.update_broadcast_message_status',
        _data={'status': new_status, 'created_by': str(approver.id)},
        service_id=t.service_id,
        broadcast_message_id=bm.id,
        _expected_status=400
    )

    assert mock_task.called is False
    assert f'from {current_status} to {new_status}' in response['message']
