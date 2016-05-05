import json
import uuid
import app.celery.tasks

from tests import create_authorization_header
from tests.app.conftest import sample_job as create_job


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


def test_create_job_returns_404_if_missing_service(notify_api, sample_template, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.process_job.apply_async')
            random_id = str(uuid.uuid4())
            data = {}
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


def _setup_jobs(notify_db, notify_db_session, template, number_of_jobs=5):
    for i in range(number_of_jobs):
        create_job(
            notify_db,
            notify_db_session,
            service=template.service,
            template=template)
