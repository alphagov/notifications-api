import datetime
import pytest
from flask import json, url_for

from app import DATETIME_FORMAT
from tests import create_authorization_header
from tests.app.db import (
    create_notification,
    create_template,
)

from tests.app.conftest import (
    sample_notification,
    sample_email_notification,
)


@pytest.mark.parametrize('billable_units, provider', [
    (1, 'mmg'),
    (0, 'mmg'),
    (1, None)
])
def test_get_notification_by_id_returns_200(
        client, billable_units, provider, sample_template
):
    sample_notification = create_notification(
        template=sample_template,
        billable_units=billable_units,
        sent_by=provider,
        scheduled_for="2017-05-12 15:15"
    )

    # another
    create_notification(
        template=sample_template,
        billable_units=billable_units,
        sent_by=provider,
        scheduled_for="2017-06-12 15:15"
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
        'body': sample_notification.template.content,
        "subject": None,
        'sent_at': sample_notification.sent_at,
        'completed_at': sample_notification.completed_at(),
        'scheduled_for': '2017-05-12T14:15:00.000000Z'
    }

    assert json_response == expected_response


def test_get_notification_by_id_with_placeholders_returns_200(
        client, sample_email_template_with_placeholders
):
    sample_notification = create_notification(
        template=sample_email_template_with_placeholders,
        personalisation={"name": "Bob"}
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
        'email_address': '{}'.format(sample_notification.to),
        'phone_number': None,
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
        'body': "Hello Bob\nThis is an email from GOV.\u200bUK",
        "subject": "Bob",
        'sent_at': sample_notification.sent_at,
        'completed_at': sample_notification.completed_at(),
        'scheduled_for': None
    }

    assert json_response == expected_response


def test_get_notification_by_reference_returns_200(client, sample_template):
    sample_notification_with_reference = create_notification(template=sample_template,
                                                             client_reference='some-client-reference')

    auth_header = create_authorization_header(service_id=sample_notification_with_reference.service_id)
    response = client.get(
        path='/v2/notifications?reference={}'.format(sample_notification_with_reference.client_reference),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 200
    assert response.headers['Content-type'] == 'application/json'

    json_response = json.loads(response.get_data(as_text=True))
    assert len(json_response['notifications']) == 1

    assert json_response['notifications'][0]['id'] == str(sample_notification_with_reference.id)
    assert json_response['notifications'][0]['reference'] == "some-client-reference"


def test_get_notifications_returns_scheduled_for(client, sample_template):
    sample_notification_with_reference = create_notification(template=sample_template,
                                                             client_reference='some-client-reference',
                                                             scheduled_for='2017-05-23 17:15')

    auth_header = create_authorization_header(service_id=sample_notification_with_reference.service_id)
    response = client.get(
        path='/v2/notifications?reference={}'.format(sample_notification_with_reference.client_reference),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 200
    assert response.headers['Content-type'] == 'application/json'

    json_response = json.loads(response.get_data(as_text=True))
    assert len(json_response['notifications']) == 1

    assert json_response['notifications'][0]['id'] == str(sample_notification_with_reference.id)
    assert json_response['notifications'][0]['scheduled_for'] == "2017-05-23T16:15:00.000000Z"


def test_get_notification_by_reference_nonexistent_reference_returns_no_notifications(client, sample_service):
    auth_header = create_authorization_header(service_id=sample_service.id)
    response = client.get(
        path='/v2/notifications?reference={}'.format('nonexistent-reference'),
        headers=[('Content-Type', 'application/json'), auth_header])

    json_response = json.loads(response.get_data(as_text=True))

    assert response.status_code == 200
    assert response.headers['Content-type'] == "application/json"
    assert len(json_response['notifications']) == 0


def test_get_notification_by_id_nonexistent_id(client, sample_notification):
    auth_header = create_authorization_header(service_id=sample_notification.service_id)
    response = client.get(
        path='/v2/notifications/dd4b8b9d-d414-4a83-9256-580046bf18f9',
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 404
    assert response.headers['Content-type'] == 'application/json'

    json_response = json.loads(response.get_data(as_text=True))
    assert json_response == {
        "errors": [
            {
                "error": "NoResultFound",
                "message": "No result found"
            }
        ],
        "status_code": 404
    }


@pytest.mark.parametrize("id", ["1234-badly-formatted-id-7890", "0"])
def test_get_notification_by_id_invalid_id(client, sample_notification, id):
    auth_header = create_authorization_header(service_id=sample_notification.service_id)
    response = client.get(
        path='/v2/notifications/{}'.format(id),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 404
    assert response.headers['Content-type'] == 'application/json'

    json_response = json.loads(response.get_data(as_text=True))
    assert json_response == {
        "message": "The requested URL was not found on the server.  "
                   "If you entered the URL manually please check your spelling and try again.",
        "result": "error"
    }


@pytest.mark.parametrize('created_at_month, estimated_delivery', [
    (
        12, '2000-12-06T16:00:00.000000Z',  # 4pm GMT in winter
    ),
    (
        6, '2000-06-05T15:00:00.000000Z',  # 4pm BST in summer
    ),
])
def test_get_notification_adds_delivery_estimate_for_letters(
    client,
    sample_letter_notification,
    created_at_month,
    estimated_delivery,
):
    sample_letter_notification.created_at = datetime.date(2000, created_at_month, 1)
    auth_header = create_authorization_header(service_id=sample_letter_notification.service_id)
    response = client.get(
        path='/v2/notifications/{}'.format(sample_letter_notification.id),
        headers=[('Content-Type', 'application/json'), auth_header]
    )

    json_response = json.loads(response.get_data(as_text=True))
    assert response.status_code == 200
    assert json_response['estimated_delivery'] == estimated_delivery


@pytest.mark.parametrize('notification_mock', [
    sample_notification,
    sample_email_notification,
])
def test_get_notification_doesnt_have_delivery_estimate_for_non_letters(
    client,
    notify_db,
    notify_db_session,
    notification_mock,
):
    mocked_notification = notification_mock(notify_db, notify_db_session)
    auth_header = create_authorization_header(service_id=mocked_notification.service_id)
    response = client.get(
        path='/v2/notifications/{}'.format(mocked_notification.id),
        headers=[('Content-Type', 'application/json'), auth_header]
    )
    assert response.status_code == 200
    assert 'estimated_delivery' not in json.loads(response.get_data(as_text=True))


def test_get_all_notifications_except_job_notifications_returns_200(client, sample_template, sample_job):
    create_notification(template=sample_template, job=sample_job)  # should not return this job notification
    notifications = [create_notification(template=sample_template) for _ in range(2)]
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
    assert not json_response['notifications'][0]['scheduled_for']


def test_get_all_notifications_with_include_jobs_arg_returns_200(
    client, sample_template, sample_job
):
    notifications = [
        create_notification(template=sample_template, job=sample_job),
        create_notification(template=sample_template)
    ]
    notification = notifications[-1]

    auth_header = create_authorization_header(service_id=notification.service_id)
    response = client.get(
        path='/v2/notifications?include_jobs=true',
        headers=[('Content-Type', 'application/json'), auth_header])

    json_response = json.loads(response.get_data(as_text=True))

    assert response.status_code == 200
    assert json_response['links']['current'].endswith("/v2/notifications?include_jobs=true")
    assert 'next' in json_response['links'].keys()
    assert len(json_response['notifications']) == 2

    assert json_response['notifications'][0]['id'] == str(notification.id)
    assert json_response['notifications'][0]['status'] == notification.status
    assert json_response['notifications'][0]['phone_number'] == notification.to
    assert json_response['notifications'][0]['type'] == notification.template.template_type
    assert not json_response['notifications'][0]['scheduled_for']


def test_get_all_notifications_no_notifications_if_no_notifications(client, sample_service):
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


def test_get_all_notifications_filter_by_template_type(client, sample_service):
    email_template = create_template(service=sample_service, template_type="email")
    sms_template = create_template(service=sample_service, template_type="sms")

    notification = create_notification(template=email_template, to_field="don.draper@scdp.biz")
    create_notification(template=sms_template)

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
        'uri': notification.template.get_link(),
        'version': 1
    }
    assert json_response['notifications'][0]['email_address'] == "don.draper@scdp.biz"
    assert json_response['notifications'][0]['type'] == "email"


def test_get_all_notifications_filter_by_template_type_invalid_template_type(client, sample_notification):
    auth_header = create_authorization_header(service_id=sample_notification.service_id)
    response = client.get(
        path='/v2/notifications?template_type=orange',
        headers=[('Content-Type', 'application/json'), auth_header])

    json_response = json.loads(response.get_data(as_text=True))

    assert response.status_code == 400
    assert response.headers['Content-type'] == "application/json"

    assert json_response['status_code'] == 400
    assert len(json_response['errors']) == 1
    assert json_response['errors'][0]['message'] == "template_type orange is not one of [sms, email, letter]"


def test_get_all_notifications_filter_by_single_status(client, sample_template):
    notification = create_notification(template=sample_template, status="pending")
    create_notification(template=sample_template)

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


def test_get_all_notifications_filter_by_status_invalid_status(client, sample_notification):
    auth_header = create_authorization_header(service_id=sample_notification.service_id)
    response = client.get(
        path='/v2/notifications?status=elephant',
        headers=[('Content-Type', 'application/json'), auth_header])

    json_response = json.loads(response.get_data(as_text=True))

    assert response.status_code == 400
    assert response.headers['Content-type'] == "application/json"

    assert json_response['status_code'] == 400
    assert len(json_response['errors']) == 1
    assert json_response['errors'][0]['message'] == "status elephant is not one of [created, sending, sent, " \
        "delivered, pending, failed, technical-failure, temporary-failure, permanent-failure, accepted, received]"


def test_get_all_notifications_filter_by_multiple_statuses(client, sample_template):
    notifications = [
        create_notification(template=sample_template, status=_status)
        for _status in ["created", "pending", "sending"]
    ]
    failed_notification = create_notification(template=sample_template, status="permanent-failure")

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


def test_get_all_notifications_filter_by_failed_status(client, sample_template):
    created_notification = create_notification(template=sample_template, status="created")
    failed_notifications = [
        create_notification(template=sample_template, status=_status)
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


def test_get_all_notifications_filter_by_id(client, sample_template):
    older_notification = create_notification(template=sample_template)
    newer_notification = create_notification(template=sample_template)

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


def test_get_all_notifications_filter_by_id_invalid_id(client, sample_notification):
    auth_header = create_authorization_header(service_id=sample_notification.service_id)
    response = client.get(
        path='/v2/notifications?older_than=1234-badly-formatted-id-7890',
        headers=[('Content-Type', 'application/json'), auth_header])

    json_response = json.loads(response.get_data(as_text=True))

    assert json_response['status_code'] == 400
    assert len(json_response['errors']) == 1
    assert json_response['errors'][0]['message'] == "older_than is not a valid UUID"


def test_get_all_notifications_filter_by_id_no_notifications_if_nonexistent_id(client, sample_template):
    notification = create_notification(template=sample_template)

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


def test_get_all_notifications_filter_by_id_no_notifications_if_last_notification(client, sample_template):
    notification = create_notification(template=sample_template)

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


def test_get_all_notifications_filter_multiple_query_parameters(client, sample_email_template):
    # this is the notification we are looking for
    older_notification = create_notification(
        template=sample_email_template, status="pending")

    # wrong status
    create_notification(template=sample_email_template)
    wrong_template = create_template(sample_email_template.service, template_type='sms')
    # wrong template
    create_notification(template=wrong_template, status="pending")

    # we only want notifications created before this one
    newer_notification = create_notification(template=sample_email_template)

    # this notification was created too recently
    create_notification(template=sample_email_template, status="pending")

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


def test_get_all_notifications_renames_letter_statuses(
    client,
    sample_letter_notification,
    sample_notification,
    sample_email_notification,
):
    auth_header = create_authorization_header(service_id=sample_letter_notification.service_id)
    response = client.get(
        path=url_for('v2_notifications.get_notifications'),
        headers=[('Content-Type', 'application/json'), auth_header]
    )

    json_response = json.loads(response.get_data(as_text=True))
    assert response.status_code == 200

    for noti in json_response['notifications']:
        if noti['type'] == 'sms' or noti['type'] == 'email':
            assert noti['status'] == 'created'
        elif noti['type'] == 'letter':
            assert noti['status'] == 'accepted'
        else:
            pytest.fail()


@pytest.mark.parametrize('db_status,expected_status', [
    ('created', 'accepted'),
    ('sending', 'accepted'),
    ('delivered', 'received'),
    ('pending', 'pending'),
    ('technical-failure', 'technical-failure')
])
def test_get_notifications_renames_letter_statuses(client, sample_letter_template, db_status, expected_status):
    letter_noti = create_notification(
        sample_letter_template,
        status=db_status,
        personalisation={'address_line_1': 'Mr Foo', 'address_line_2': '1 Bar Street', 'postcode': 'N1'}
    )
    auth_header = create_authorization_header(service_id=letter_noti.service_id)
    response = client.get(
        path=url_for('v2_notifications.get_notification_by_id', id=letter_noti.id),
        headers=[('Content-Type', 'application/json'), auth_header]
    )

    json_response = json.loads(response.get_data(as_text=True))
    assert response.status_code == 200
    assert json_response['status'] == expected_status
