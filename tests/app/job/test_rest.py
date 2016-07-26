import json
import uuid
from datetime import datetime, timedelta

import pytest

import app.celery.tasks

from tests import create_authorization_header
from tests.app.conftest import (
    sample_job as create_job,
    sample_notification as create_sample_notification)
from app.dao.templates_dao import dao_update_template
from app.models import NOTIFICATION_STATUS_TYPES


def test_get_jobs(notify_api, notify_db, notify_db_session, sample_template):
    _setup_jobs(notify_db, notify_db_session, sample_template)

    service_id = sample_template.service.id

    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            path = '/service/{}/job'.format(service_id)
            auth_header = create_authorization_header(service_id=service_id)
            response = client.get(path, headers=[auth_header])
            assert response.status_code == 200
            resp_json = json.loads(response.get_data(as_text=True))
            assert len(resp_json['data']) == 5


def test_get_jobs_with_limit_days(notify_api, notify_db, notify_db_session, sample_template):
    create_job(
        notify_db,
        notify_db_session,
        service=sample_template.service,
        template=sample_template,
    )
    create_job(
        notify_db,
        notify_db_session,
        service=sample_template.service,
        template=sample_template,
        created_at=datetime.now() - timedelta(days=7))

    service_id = sample_template.service.id

    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            path = '/service/{}/job'.format(service_id)
            auth_header = create_authorization_header(service_id=service_id)
            response = client.get(path, headers=[auth_header], query_string={'limit_days': 5})
            assert response.status_code == 200
            resp_json = json.loads(response.get_data(as_text=True))
            assert len(resp_json['data']) == 1


def test_get_job_with_invalid_service_id_returns404(notify_api, sample_api_key, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            path = '/service/{}/job'.format(sample_service.id)
            auth_header = create_authorization_header(service_id=sample_service.id)
            response = client.get(path, headers=[auth_header])
            assert response.status_code == 200
            resp_json = json.loads(response.get_data(as_text=True))
            assert len(resp_json['data']) == 0


def test_get_job_with_invalid_job_id_returns404(notify_api, sample_template):
    service_id = sample_template.service.id
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            path = '/service/{}/job/{}'.format(service_id, "bad-id")
            auth_header = create_authorization_header(service_id=sample_template.service.id)
            response = client.get(path, headers=[auth_header])
            assert response.status_code == 404
            resp_json = json.loads(response.get_data(as_text=True))
            assert resp_json['result'] == 'error'
            assert resp_json['message'] == 'No result found'


def test_get_job_with_unknown_id_returns404(notify_api, sample_template, fake_uuid):
    service_id = sample_template.service.id
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            path = '/service/{}/job/{}'.format(service_id, fake_uuid)
            auth_header = create_authorization_header(service_id=sample_template.service.id)
            response = client.get(path, headers=[auth_header])
            assert response.status_code == 404
            resp_json = json.loads(response.get_data(as_text=True))
            assert resp_json == {
                'message': 'No result found',
                'result': 'error'
            }


def test_get_job_by_id(notify_api, sample_job):
    job_id = str(sample_job.id)
    service_id = sample_job.service.id
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            path = '/service/{}/job/{}'.format(service_id, job_id)
            auth_header = create_authorization_header(service_id=sample_job.service.id)
            response = client.get(path, headers=[auth_header])
            assert response.status_code == 200
            resp_json = json.loads(response.get_data(as_text=True))
            assert resp_json['data']['id'] == job_id
            assert resp_json['data']['created_by']['name'] == 'Test User'


def test_create_job(notify_api, sample_template, mocker, fake_uuid):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.process_job.apply_async')
            data = {
                'id': fake_uuid,
                'service': str(sample_template.service.id),
                'template': str(sample_template.id),
                'original_file_name': 'thisisatest.csv',
                'notification_count': 1,
                'created_by': str(sample_template.created_by.id)
            }
            path = '/service/{}/job'.format(sample_template.service.id)
            auth_header = create_authorization_header(service_id=sample_template.service.id)
            headers = [('Content-Type', 'application/json'), auth_header]
            response = client.post(
                path,
                data=json.dumps(data),
                headers=headers)
            assert response.status_code == 201

            app.celery.tasks.process_job.apply_async.assert_called_once_with(
                ([str(fake_uuid)]),
                queue="process-job"
            )

            resp_json = json.loads(response.get_data(as_text=True))

            assert resp_json['data']['id'] == fake_uuid
            assert resp_json['data']['service'] == str(sample_template.service.id)
            assert resp_json['data']['template'] == str(sample_template.id)
            assert resp_json['data']['original_file_name'] == 'thisisatest.csv'


def test_create_job_returns_400_if_missing_data(notify_api, sample_template, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.process_job.apply_async')
            data = {
                'template': str(sample_template.id)
            }
            path = '/service/{}/job'.format(sample_template.service.id)
            auth_header = create_authorization_header(service_id=sample_template.service.id)
            headers = [('Content-Type', 'application/json'), auth_header]
            response = client.post(
                path,
                data=json.dumps(data),
                headers=headers)

            resp_json = json.loads(response.get_data(as_text=True))
            assert response.status_code == 400

            app.celery.tasks.process_job.apply_async.assert_not_called()
            assert resp_json['result'] == 'error'
            assert 'Missing data for required field.' in resp_json['message']['original_file_name']
            assert 'Missing data for required field.' in resp_json['message']['notification_count']
            assert 'Missing data for required field.' in resp_json['message']['id']


def test_create_job_returns_404_if_template_does_not_exist(notify_api, sample_service, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.process_job.apply_async')
            data = {
                'template': str(sample_service.id)
            }
            path = '/service/{}/job'.format(sample_service.id)
            auth_header = create_authorization_header(service_id=sample_service.id)
            headers = [('Content-Type', 'application/json'), auth_header]
            response = client.post(
                path,
                data=json.dumps(data),
                headers=headers)

            resp_json = json.loads(response.get_data(as_text=True))
            assert response.status_code == 404

            app.celery.tasks.process_job.apply_async.assert_not_called()
            assert resp_json['result'] == 'error'
            assert resp_json['message'] == 'No result found'


def test_create_job_returns_404_if_missing_service(notify_api, sample_template, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.process_job.apply_async')
            random_id = str(uuid.uuid4())
            data = {'template': str(sample_template.id)}
            path = '/service/{}/job'.format(random_id)
            auth_header = create_authorization_header(service_id=sample_template.service.id)
            headers = [('Content-Type', 'application/json'), auth_header]
            response = client.post(
                path,
                data=json.dumps(data),
                headers=headers)

            resp_json = json.loads(response.get_data(as_text=True))
            assert response.status_code == 404

            app.celery.tasks.process_job.apply_async.assert_not_called()
            assert resp_json['result'] == 'error'
            assert resp_json['message'] == 'No result found'


def test_create_job_returns_400_if_archived_template(notify_api, sample_template, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.process_job.apply_async')
            sample_template.archived = True
            dao_update_template(sample_template)
            data = {
                'template': str(sample_template.id)
            }
            path = '/service/{}/job'.format(sample_template.service.id)
            auth_header = create_authorization_header(service_id=sample_template.service.id)
            headers = [('Content-Type', 'application/json'), auth_header]
            response = client.post(
                path,
                data=json.dumps(data),
                headers=headers)

            resp_json = json.loads(response.get_data(as_text=True))
            assert response.status_code == 400

            app.celery.tasks.process_job.apply_async.assert_not_called()
            assert resp_json['result'] == 'error'
            assert 'Template has been deleted' in resp_json['message']['template']


def _setup_jobs(notify_db, notify_db_session, template, number_of_jobs=5):
    for i in range(number_of_jobs):
        create_job(
            notify_db,
            notify_db_session,
            service=template.service,
            template=template)


def test_get_all_notifications_for_job_in_order_of_job_number(notify_api,
                                                              notify_db,
                                                              notify_db_session,
                                                              sample_service):
    with notify_api.test_request_context(), notify_api.test_client() as client:
        main_job = create_job(notify_db, notify_db_session, service=sample_service)
        another_job = create_job(notify_db, notify_db_session, service=sample_service)

        notification_1 = create_sample_notification(
            notify_db,
            notify_db_session,
            job=main_job,
            to_field="1",
            created_at=datetime.utcnow(),
            job_row_number=1
        )
        notification_2 = create_sample_notification(
            notify_db,
            notify_db_session,
            job=main_job,
            to_field="2",
            created_at=datetime.utcnow(),
            job_row_number=2
        )
        notification_3 = create_sample_notification(
            notify_db,
            notify_db_session,
            job=main_job,
            to_field="3",
            created_at=datetime.utcnow(),
            job_row_number=3
        )
        create_sample_notification(notify_db, notify_db_session, job=another_job)

        auth_header = create_authorization_header()

        response = client.get(
            path='/service/{}/job/{}/notifications'.format(sample_service.id, main_job.id),
            headers=[auth_header])

        resp = json.loads(response.get_data(as_text=True))
        assert len(resp['notifications']) == 3
        assert resp['notifications'][0]['to'] == notification_1.to
        assert resp['notifications'][0]['job_row_number'] == notification_1.job_row_number
        assert resp['notifications'][1]['to'] == notification_2.to
        assert resp['notifications'][1]['job_row_number'] == notification_2.job_row_number
        assert resp['notifications'][2]['to'] == notification_3.to
        assert resp['notifications'][2]['job_row_number'] == notification_3.job_row_number
        assert response.status_code == 200


@pytest.mark.parametrize(
    "expected_notification_count, status_args",
    [
        (
            1,
            '?status={}'.format(NOTIFICATION_STATUS_TYPES[0])
        ),
        (
            0,
            '?status={}'.format(NOTIFICATION_STATUS_TYPES[1])
        ),
        (
            1,
            '?status={}&status={}&status={}'.format(
                *NOTIFICATION_STATUS_TYPES[0:3]
            )
        ),
        (
            0,
            '?status={}&status={}&status={}'.format(
                *NOTIFICATION_STATUS_TYPES[3:6]
            )
        ),
    ]
)
def test_get_all_notifications_for_job_filtered_by_status(
    notify_api,
    notify_db,
    notify_db_session,
    sample_service,
    expected_notification_count,
    status_args
):
    with notify_api.test_request_context(), notify_api.test_client() as client:
        job = create_job(notify_db, notify_db_session, service=sample_service)

        create_sample_notification(
            notify_db,
            notify_db_session,
            job=job,
            to_field="1",
            created_at=datetime.utcnow(),
            status=NOTIFICATION_STATUS_TYPES[0],
            job_row_number=1
        )

        response = client.get(
            path='/service/{}/job/{}/notifications{}'.format(sample_service.id, job.id, status_args),
            headers=[create_authorization_header()]
        )
        resp = json.loads(response.get_data(as_text=True))
        assert len(resp['notifications']) == expected_notification_count
        assert response.status_code == 200
