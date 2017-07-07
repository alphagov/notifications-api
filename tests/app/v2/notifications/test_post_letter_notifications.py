import uuid

from flask import url_for, json
import pytest

from app.models import Job, Notification, SMS_TYPE, EMAIL_TYPE, LETTER_TYPE
from app.v2.errors import RateLimitError

from tests import create_authorization_header
from tests.app.db import create_service, create_template


def letter_request(client, data, service_id, _expected_status=201):
    resp = client.post(
        url_for('v2_notifications.post_notification', notification_type='letter'),
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), create_authorization_header(service_id=service_id)]
    )
    assert resp.status_code == _expected_status
    json_resp = json.loads(resp.get_data(as_text=True))
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
    notification = Notification.query.all()
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

    mocked.assert_called_once_with((str(job.id), ), queue='job-tasks')


def test_post_letter_notification_returns_400_and_missing_template(
    client,
    sample_service
):
    data = {
        'template_id': str(uuid.uuid4()),
        'personalisation': {'address_line_1': '', 'postcode': ''}
    }

    error_json = letter_request(client, data, service_id=sample_service.id, _expected_status=400)

    assert error_json['status_code'] == 400
    assert error_json['errors'] == [{'error': 'BadRequestError', 'message': 'Template not found'}]



def test_post_notification_returns_403_and_well_formed_auth_error(
    client,
    sample_letter_template
):
    data = {
        'template_id': str(sample_letter_template.id),
        'personalisation': {'address_line_1': '', 'postcode': ''}
    }

    error_json = letter_request(client, data, service_id=sample_letter_template.service_id, _expected_status=401)

    assert error_json['status_code'] == 401
    assert error_json['errors'] == [{
        'error': 'AuthError',
        'message': 'Unauthorized, authentication token must be provided'
    }]


def test_notification_returns_400_for_schema_problems(
    client,
    sample_service
):
    data = {
        'personalisation': {'address_line_1': '', 'postcode': ''}
    }

    error_json = letter_request(client, data, service_id=sample_service.id, _expected_status=400)

    assert error_json['status_code'] == 400
    assert error_json['errors'] == [{
        'error': 'ValidationError',
        'message': 'template_id is a required property'
    }]


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
        'personalisation': {'address_line_1': '', 'postcode': ''}
    }

    error_json = letter_request(client, data, service_id=sample_letter_template.service_id, _expected_status=429)

    assert error_json['status_code'] == 429
    assert error_json['errors'] == [{
        'error': 'RateLimitError',
        'message': 'Exceeded rate limit for key type TYPE of LIMIT requests per INTERVAL seconds'
    }]

    assert not persist_mock.called


def test_post_letter_notification_returns_400_if_not_allowed_to_send_notification(
    client,
    notify_db_session
):
    service = create_service(service_permissions=[EMAIL_TYPE, SMS_TYPE])
    template = create_template(service, template_type=LETTER_TYPE)

    data = {
        'template_id': str(template.id),
        'personalisation': {'address_line_1': '', 'postcode': ''}
    }

    error_json = letter_request(client, data, service_id=service.id, _expected_status=400)
    assert error_json['status_code'] == 400
    assert error_json['errors'] == [
        {'error': 'BadRequestError', 'message': 'Cannot send text letters'}
    ]
