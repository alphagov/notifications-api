from tests import create_authorization_header
from flask import json

from tests.app.conftest import sample_job, sample_notification

top_level_notification_keys = [
    'created_at',
    'template_version',
    'reference',
    'id',
    'sent_at',
    'updated_at',
    'template',
    'notification_type',
    'api_key',
    'to',
    'status',
    'content_char_count',
    'job_row_number',
    'job',
    'sent_by',
    'billable_units',
    'service',
    'body']

template_keys = [
    'template_type',
    'name',
    'id',
    'version'
]

jobs_keys = [
    'id',
    'original_file_name',
]


def test_api_response_for_get_job_sms_notification_by_id(
        notify_db,
        notify_db_session,
        notify_api,
        sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            job = sample_job(notify_db, notify_db_session, service=sample_service)
            notification = sample_notification(notify_db, notify_db_session, service=sample_service, job=job)

            auth_header = create_authorization_header(service_id=sample_service.id)

            response = client.get(
                '/notifications/{}'.format(notification.id),
                headers=[auth_header])

            notification_json = json.loads(response.get_data(as_text=True))
            print(notification_json)
            assert 'data' in notification_json
            assert 'notification' in notification_json['data']

            notification = notification_json['data']['notification']

            assert sorted(top_level_notification_keys) == sorted(notification.keys())
            assert sorted(template_keys) == sorted(notification['template'].keys())
            assert sorted(jobs_keys) == sorted(notification['job'].keys())

            assert response.status_code == 200


def test_api_response_for_get_api_sms_notification_by_id():
    assert 1 == 2


def test_api_response_for_get_job_email_notification_by_id():
    assert 1 == 2


def test_api_response_for_get_api_email_notification_by_id():
    assert 1 == 2


def test_api_response_for_get_all_notifications_for_service():
    assert 1 == 2
