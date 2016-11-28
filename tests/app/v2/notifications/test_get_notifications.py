import json
import pytest

from app import DATETIME_FORMAT
from tests import create_authorization_header
from tests.app.conftest import (
    sample_notification as create_sample_notification,
    sample_template as create_sample_template
)


@pytest.mark.parametrize('billable_units, provider', [
    (1, 'mmg'),
    (0, 'mmg'),
    (1, None)
])
def test_get_notification_by_id_returns_200(
        client, notify_db, notify_db_session, sample_provider_rate, billable_units, provider
):
    sample_notification = create_sample_notification(
        notify_db, notify_db_session, billable_units=billable_units, sent_by=provider
    )

    auth_header = create_authorization_header(service_id=sample_notification.service_id)
    response = client.get(
        path='/v2/notifications/{}'.format(sample_notification.id),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 200
    assert response.headers['Content-type'] == 'application/json'

    json_response = json.loads(response.get_data(as_text=True))

    expected_template_response = {
        'id': '{}'.format(sample_notification.serialize()['template']['id']),
        'version': sample_notification.serialize()['template']['version'],
        'uri': sample_notification.serialize()['template']['uri']
    }

    expected_response = {
        'id': '{}'.format(sample_notification.id),
        'reference': None,
        'email_address': None,
        'phone_number': '{}'.format(sample_notification.to),
        'line_1': None,
        'line_2': None,
        'line_3': None,
        'line_4': None,
        'line_5': None,
        'line_6': None,
        'postcode': None,
        'type': '{}'.format(sample_notification.notification_type),
        'status': '{}'.format(sample_notification.status),
        'template': expected_template_response,
        'created_at': sample_notification.created_at.strftime(DATETIME_FORMAT),
        'sent_at': sample_notification.sent_at,
        'completed_at': sample_notification.completed_at()
    }

    assert json_response == expected_response


def test_get_all_notifications_returns_200(client, notify_db, notify_db_session):
    notifications = [create_sample_notification(notify_db, notify_db_session) for _ in range(2)]
    notification = notifications[-1]

    auth_header = create_authorization_header(service_id=notification.service_id)
    response = client.get(
        path='/v2/notifications',
        headers=[('Content-Type', 'application/json'), auth_header])

    json_response = json.loads(response.get_data(as_text=True))

    assert response.status_code == 200
    assert response.headers['Content-type'] == "application/json"
    assert json_response['links']['current'].endswith("/v2/notifications")
    assert 'next' in json_response['links'].keys()
    assert len(json_response['notifications']) == 2

    assert json_response['notifications'][0]['id'] == str(notification.id)
    assert json_response['notifications'][0]['status'] == "created"
    assert json_response['notifications'][0]['template'] == {
        'id': str(notification.template.id),
        'uri': notification.template.get_link(),
        'version': 1
    }
    assert json_response['notifications'][0]['phone_number'] == "+447700900855"
    assert json_response['notifications'][0]['type'] == "sms"


def test_get_all_notifications_no_notifications_if_no_notificatons(client, sample_service):
    auth_header = create_authorization_header(service_id=sample_service.id)
    response = client.get(
        path='/v2/notifications',
        headers=[('Content-Type', 'application/json'), auth_header])

    json_response = json.loads(response.get_data(as_text=True))

    assert response.status_code == 200
    assert response.headers['Content-type'] == "application/json"
    assert json_response['links']['current'].endswith("/v2/notifications")
    assert 'next' not in json_response['links'].keys()
    assert len(json_response['notifications']) == 0


def test_get_all_notifications_filter_by_template_type(client, notify_db, notify_db_session):
    email_template = create_sample_template(notify_db, notify_db_session, template_type="email")
    sms_template = create_sample_template(notify_db, notify_db_session, template_type="sms")

    notification = create_sample_notification(
        notify_db, notify_db_session, template=email_template, to_field="don.draper@scdp.biz")
    create_sample_notification(notify_db, notify_db_session, template=sms_template)

    auth_header = create_authorization_header(service_id=notification.service_id)
    response = client.get(
        path='/v2/notifications?template_type=email',
        headers=[('Content-Type', 'application/json'), auth_header])

    json_response = json.loads(response.get_data(as_text=True))

    assert response.status_code == 200
    assert response.headers['Content-type'] == "application/json"
    assert json_response['links']['current'].endswith("/v2/notifications?template_type=email")
    assert 'next' in json_response['links'].keys()
    assert len(json_response['notifications']) == 1

    assert json_response['notifications'][0]['id'] == str(notification.id)
    assert json_response['notifications'][0]['status'] == "created"
    assert json_response['notifications'][0]['template'] == {
        'id': str(email_template.id),
        'uri': email_template.get_link(),
        'version': 1
    }
    assert json_response['notifications'][0]['email_address'] == "don.draper@scdp.biz"
    assert json_response['notifications'][0]['type'] == "email"


def test_get_all_notifications_filter_by_single_status(client, notify_db, notify_db_session):
    notification = create_sample_notification(notify_db, notify_db_session, status="pending")
    create_sample_notification(notify_db, notify_db_session)

    auth_header = create_authorization_header(service_id=notification.service_id)
    response = client.get(
        path='/v2/notifications?status=pending',
        headers=[('Content-Type', 'application/json'), auth_header])

    json_response = json.loads(response.get_data(as_text=True))

    assert response.status_code == 200
    assert response.headers['Content-type'] == "application/json"
    assert json_response['links']['current'].endswith("/v2/notifications?status=pending")
    assert 'next' in json_response['links'].keys()
    assert len(json_response['notifications']) == 1

    assert json_response['notifications'][0]['id'] == str(notification.id)
    assert json_response['notifications'][0]['status'] == "pending"


def test_get_all_notifications_filter_by_multiple_statuses(client, notify_db, notify_db_session):
    notifications = [
        create_sample_notification(notify_db, notify_db_session, status=_status)
        for _status in ["created", "pending", "sending"]
    ]
    failed_notification = create_sample_notification(notify_db, notify_db_session, status="permanent-failure")

    auth_header = create_authorization_header(service_id=notifications[0].service_id)
    response = client.get(
        path='/v2/notifications?status=created&status=pending&status=sending',
        headers=[('Content-Type', 'application/json'), auth_header])

    json_response = json.loads(response.get_data(as_text=True))

    assert response.status_code == 200
    assert response.headers['Content-type'] == "application/json"
    assert json_response['links']['current'].endswith("/v2/notifications?status=created&status=pending&status=sending")
    assert 'next' in json_response['links'].keys()
    assert len(json_response['notifications']) == 3

    returned_notification_ids = [_n['id'] for _n in json_response['notifications']]
    for _id in [_notification.id for _notification in notifications]:
        assert str(_id) in returned_notification_ids

    assert failed_notification.id not in returned_notification_ids


def test_get_all_notifications_filter_by_failed_status(client, notify_db, notify_db_session):
    created_notification = create_sample_notification(notify_db, notify_db_session, status="created")
    failed_notifications = [
        create_sample_notification(notify_db, notify_db_session, status=_status)
        for _status in ["technical-failure", "temporary-failure", "permanent-failure"]
    ]

    auth_header = create_authorization_header(service_id=created_notification.service_id)
    response = client.get(
        path='/v2/notifications?status=failed',
        headers=[('Content-Type', 'application/json'), auth_header])

    json_response = json.loads(response.get_data(as_text=True))

    assert response.status_code == 200
    assert response.headers['Content-type'] == "application/json"
    assert json_response['links']['current'].endswith("/v2/notifications?status=failed")
    assert 'next' in json_response['links'].keys()
    assert len(json_response['notifications']) == 3

    returned_notification_ids = [n['id'] for n in json_response['notifications']]
    for _id in [_notification.id for _notification in failed_notifications]:
        assert str(_id) in returned_notification_ids

    assert created_notification.id not in returned_notification_ids


def test_get_all_notifications_filter_by_id(client, notify_db, notify_db_session):
    older_notification = create_sample_notification(notify_db, notify_db_session)
    newer_notification = create_sample_notification(notify_db, notify_db_session)

    auth_header = create_authorization_header(service_id=newer_notification.service_id)
    response = client.get(
        path='/v2/notifications?older_than={}'.format(newer_notification.id),
        headers=[('Content-Type', 'application/json'), auth_header])

    json_response = json.loads(response.get_data(as_text=True))

    assert response.status_code == 200
    assert response.headers['Content-type'] == "application/json"
    assert json_response['links']['current'].endswith("/v2/notifications?older_than={}".format(newer_notification.id))
    assert 'next' in json_response['links'].keys()
    assert len(json_response['notifications']) == 1

    assert json_response['notifications'][0]['id'] == str(older_notification.id)


def test_get_all_notifications_filter_by_id_no_notifications_if_nonexistent_id(client, notify_db, notify_db_session):
    notification = create_sample_notification(notify_db, notify_db_session)

    auth_header = create_authorization_header(service_id=notification.service_id)
    response = client.get(
        path='/v2/notifications?older_than=dd4b8b9d-d414-4a83-9256-580046bf18f9',
        headers=[('Content-Type', 'application/json'), auth_header])

    json_response = json.loads(response.get_data(as_text=True))

    assert response.status_code == 200
    assert response.headers['Content-type'] == "application/json"
    assert json_response['links']['current'].endswith(
        "/v2/notifications?older_than=dd4b8b9d-d414-4a83-9256-580046bf18f9")
    assert 'next' not in json_response['links'].keys()
    assert len(json_response['notifications']) == 0


def test_get_all_notifications_filter_by_id_no_notifications_if_last_notification(client, notify_db, notify_db_session):
    notification = create_sample_notification(notify_db, notify_db_session)

    auth_header = create_authorization_header(service_id=notification.service_id)
    response = client.get(
        path='/v2/notifications?older_than={}'.format(notification.id),
        headers=[('Content-Type', 'application/json'), auth_header])

    json_response = json.loads(response.get_data(as_text=True))

    assert response.status_code == 200
    assert response.headers['Content-type'] == "application/json"
    assert json_response['links']['current'].endswith("/v2/notifications?older_than={}".format(notification.id))
    assert 'next' not in json_response['links'].keys()
    assert len(json_response['notifications']) == 0


def test_get_all_notifications_filter_multiple_query_parameters(client, notify_db, notify_db_session):
    email_template = create_sample_template(notify_db, notify_db_session, template_type="email")

    # this is the notification we are looking for
    older_notification = create_sample_notification(
        notify_db, notify_db_session, template=email_template, status="pending")

    # wrong status
    create_sample_notification(notify_db, notify_db_session, template=email_template)
    # wrong template
    create_sample_notification(notify_db, notify_db_session, status="pending")

    # we only want notifications created before this one
    newer_notification = create_sample_notification(notify_db, notify_db_session)

    # this notification was created too recently
    create_sample_notification(notify_db, notify_db_session, template=email_template, status="pending")

    auth_header = create_authorization_header(service_id=newer_notification.service_id)
    response = client.get(
        path='/v2/notifications?status=pending&template_type=email&older_than={}'.format(newer_notification.id),
        headers=[('Content-Type', 'application/json'), auth_header])

    json_response = json.loads(response.get_data(as_text=True))

    assert response.status_code == 200
    assert response.headers['Content-type'] == "application/json"
    # query parameters aren't returned in order
    for url_part in [
        "/v2/notifications?",
        "template_type=email",
        "status=pending",
        "older_than={}".format(newer_notification.id)
    ]:
        assert url_part in json_response['links']['current']

    assert 'next' in json_response['links'].keys()
    assert len(json_response['notifications']) == 1

    assert json_response['notifications'][0]['id'] == str(older_notification.id)
