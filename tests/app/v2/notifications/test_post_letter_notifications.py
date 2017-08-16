import uuid

from flask import json
from flask import url_for
import pytest

from app.models import EMAIL_TYPE
from app.models import Job
from app.models import KEY_TYPE_NORMAL
from app.models import KEY_TYPE_TEAM
from app.models import KEY_TYPE_TEST
from app.models import LETTER_TYPE
from app.models import Notification
from app.models import SMS_TYPE
from app.v2.errors import RateLimitError
from app.variables import LETTER_TEST_API_FILENAME
from app.variables import LETTER_API_FILENAME

from tests import create_authorization_header
from tests.app.db import create_service
from tests.app.db import create_template


def letter_request(client, data, service_id, key_type=KEY_TYPE_NORMAL, _expected_status=201):
    resp = client.post(
        url_for('v2_notifications.post_notification', notification_type='letter'),
        data=json.dumps(data),
        headers=[
            ('Content-Type', 'application/json'),
            create_authorization_header(service_id=service_id, key_type=key_type)
        ]
    )
    json_resp = json.loads(resp.get_data(as_text=True))
    assert resp.status_code == _expected_status, json_resp
    return json_resp


@pytest.mark.parametrize('reference', [None, 'reference_from_client'])
def test_post_letter_notification_returns_201(client, sample_letter_template, mocker, reference):
    mocked = mocker.patch('app.celery.tasks.build_dvla_file.apply_async')
    data = {
        'template_id': str(sample_letter_template.id),
        'personalisation': {
            'address_line_1': 'Her Royal Highness Queen Elizabeth II',
            'address_line_2': 'Buckingham Palace',
            'address_line_3': 'London',
            'postcode': 'SW1 1AA',
            'name': 'Lizzie'
        }
    }

    if reference:
        data.update({'reference': reference})

    resp_json = letter_request(client, data, service_id=sample_letter_template.service_id)

    job = Job.query.one()
    assert job.original_file_name == LETTER_API_FILENAME
    notification = Notification.query.one()
    notification_id = notification.id
    assert resp_json['id'] == str(notification_id)
    assert resp_json['reference'] == reference
    assert resp_json['content']['subject'] == sample_letter_template.subject
    assert resp_json['content']['body'] == sample_letter_template.content
    assert 'v2/notifications/{}'.format(notification_id) in resp_json['uri']
    assert resp_json['template']['id'] == str(sample_letter_template.id)
    assert resp_json['template']['version'] == sample_letter_template.version
    assert (
        'services/{}/templates/{}'.format(
            sample_letter_template.service_id,
            sample_letter_template.id
        ) in resp_json['template']['uri']
    )
    assert not resp_json['scheduled_for']

    mocked.assert_called_once_with([str(job.id)], queue='job-tasks')


def test_post_letter_notification_returns_400_and_missing_template(
    client,
    sample_service_full_permissions
):
    data = {
        'template_id': str(uuid.uuid4()),
        'personalisation': {'address_line_1': '', 'address_line_2': '', 'postcode': ''}
    }

    error_json = letter_request(client, data, service_id=sample_service_full_permissions.id, _expected_status=400)

    assert error_json['status_code'] == 400
    assert error_json['errors'] == [{'error': 'BadRequestError', 'message': 'Template not found'}]


def test_notification_returns_400_for_missing_template_field(
    client,
    sample_service_full_permissions
):
    data = {
        'personalisation': {'address_line_1': '', 'address_line_2': '', 'postcode': ''}
    }

    error_json = letter_request(client, data, service_id=sample_service_full_permissions.id, _expected_status=400)

    assert error_json['status_code'] == 400
    assert error_json['errors'] == [{
        'error': 'ValidationError',
        'message': 'template_id is a required property'
    }]


def test_notification_returns_400_if_address_doesnt_have_underscores(
    client,
    sample_letter_template
):
    data = {
        'template_id': str(sample_letter_template.id),
        'personalisation': {
            'address line 1': 'Her Royal Highness Queen Elizabeth II',
            'address-line-2': 'Buckingham Palace',
            'postcode': 'SW1 1AA',
        }
    }

    error_json = letter_request(client, data, service_id=sample_letter_template.service_id, _expected_status=400)

    assert error_json['status_code'] == 400
    assert len(error_json['errors']) == 2
    assert {
        'error': 'ValidationError',
        'message': 'personalisation address_line_1 is a required property'
    } in error_json['errors']
    assert {
        'error': 'ValidationError',
        'message': 'personalisation address_line_2 is a required property'
    } in error_json['errors']


def test_returns_a_429_limit_exceeded_if_rate_limit_exceeded(
    client,
    sample_letter_template,
    mocker
):
    persist_mock = mocker.patch('app.v2.notifications.post_notifications.persist_notification')
    mocker.patch(
        'app.v2.notifications.post_notifications.check_rate_limiting',
        side_effect=RateLimitError('LIMIT', 'INTERVAL', 'TYPE')
    )

    data = {
        'template_id': str(sample_letter_template.id),
        'personalisation': {'address_line_1': '', 'address_line_2': '', 'postcode': ''}
    }

    error_json = letter_request(client, data, service_id=sample_letter_template.service_id, _expected_status=429)

    assert error_json['status_code'] == 429
    assert error_json['errors'] == [{
        'error': 'RateLimitError',
        'message': 'Exceeded rate limit for key type TYPE of LIMIT requests per INTERVAL seconds'
    }]

    assert not persist_mock.called


@pytest.mark.parametrize('service_args', [
    {'service_permissions': [EMAIL_TYPE, SMS_TYPE]},
    {'restricted': True}
])
def test_post_letter_notification_returns_403_if_not_allowed_to_send_notification(
    client,
    notify_db_session,
    service_args
):
    service = create_service(**service_args)
    template = create_template(service, template_type=LETTER_TYPE)

    data = {
        'template_id': str(template.id),
        'personalisation': {'address_line_1': '', 'address_line_2': '', 'postcode': ''}
    }

    error_json = letter_request(client, data, service_id=service.id, _expected_status=400)
    assert error_json['status_code'] == 400
    assert error_json['errors'] == [
        {'error': 'BadRequestError', 'message': 'Cannot send letters'}
    ]


@pytest.mark.parametrize('research_mode, key_type', [
    (True, KEY_TYPE_NORMAL),
    (False, KEY_TYPE_TEST)
])
def test_post_letter_notification_doesnt_queue_task(
    client,
    notify_db_session,
    mocker,
    research_mode,
    key_type
):
    real_task = mocker.patch('app.celery.tasks.build_dvla_file.apply_async')
    fake_task = mocker.patch('app.celery.tasks.update_job_to_sent_to_dvla.apply_async')

    service = create_service(research_mode=research_mode, service_permissions=[LETTER_TYPE])
    template = create_template(service, template_type=LETTER_TYPE)

    data = {
        'template_id': str(template.id),
        'personalisation': {'address_line_1': 'Foo', 'address_line_2': 'Bar', 'postcode': 'Baz'}
    }

    letter_request(client, data, service_id=service.id, key_type=key_type)

    job = Job.query.one()
    assert job.original_file_name == LETTER_TEST_API_FILENAME
    assert not real_task.called
    fake_task.assert_called_once_with([str(job.id)], queue='research-mode-tasks')


def test_post_letter_notification_doesnt_accept_team_key(client, sample_letter_template):
    data = {
        'template_id': str(sample_letter_template.id),
        'personalisation': {'address_line_1': 'Foo', 'address_line_2': 'Bar', 'postcode': 'Baz'}
    }

    error_json = letter_request(
        client,
        data,
        sample_letter_template.service_id,
        key_type=KEY_TYPE_TEAM,
        _expected_status=403
    )

    assert error_json['status_code'] == 403
    assert error_json['errors'] == [{'error': 'BadRequestError', 'message': 'Cannot send letters with a team api key'}]
