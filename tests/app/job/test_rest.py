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
            auth_header = create_authorization_header(
                service_id=service_id,
                path=path,
                method='GET')
            response = client.get(path, headers=[auth_header])
            assert response.status_code == 200
            resp_json = json.loads(response.get_data(as_text=True))
            assert len(resp_json['data']) == 5


def test_get_job_with_invalid_service_id_returns404(notify_api, sample_api_key, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            path = '/service/{}/job'.format(sample_service.id)
            auth_header = create_authorization_header(
                service_id=sample_service.id,
                path=path,
                method='GET')
            response = client.get(path, headers=[auth_header])
            assert response.status_code == 200
            resp_json = json.loads(response.get_data(as_text=True))
            assert len(resp_json['data']) == 0


def test_get_job_with_invalid_job_id_returns404(notify_api, sample_template):
    service_id = sample_template.service.id
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            path = '/service/{}/job/{}'.format(service_id, "bad-id")
            auth_header = create_authorization_header(
                service_id=sample_template.service.id,
                path=path,
                method='GET')
            response = client.get(path, headers=[auth_header])
            assert response.status_code == 404
            resp_json = json.loads(response.get_data(as_text=True))
            assert resp_json['result'] == 'error'
            assert resp_json['message'] == 'No result found'


def test_get_job_with_unknown_id_returns404(notify_api, sample_template):
    random_id = str(uuid.uuid4())
    service_id = sample_template.service.id
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            path = '/service/{}/job/{}'.format(service_id, random_id)
            auth_header = create_authorization_header(
                service_id=sample_template.service.id,
                path=path,
                method='GET')
            response = client.get(path, headers=[auth_header])
            assert response.status_code == 404
            resp_json = json.loads(response.get_data(as_text=True))
            assert resp_json == {
                'message': 'Job {} not found for service {}'.format(random_id, service_id),
                'result': 'error'
            }


def test_get_job_by_id(notify_api, sample_job):
    job_id = str(sample_job.id)
    service_id = sample_job.service.id
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            path = '/service/{}/job/{}'.format(service_id, job_id)
            auth_header = create_authorization_header(
                service_id=sample_job.service.id,
                path=path,
                method='GET')
            response = client.get(path, headers=[auth_header])
            assert response.status_code == 200
            resp_json = json.loads(response.get_data(as_text=True))
            assert resp_json['data']['id'] == job_id


def test_create_job(notify_api, sample_template, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.process_job.apply_async')
            job_id = uuid.uuid4()
            data = {
                'id': str(job_id),
                'service': str(sample_template.service.id),
                'template': sample_template.id,
                'original_file_name': 'thisisatest.csv',
                'bucket_name': 'service-{}-notify'.format(sample_template.service.id),
                'file_name': '{}.csv'.format(job_id),
                'notification_count': 1
            }
            path = '/service/{}/job'.format(sample_template.service.id)
            auth_header = create_authorization_header(
                service_id=sample_template.service.id,
                path=path,
                method='POST',
                request_body=json.dumps(data))
            headers = [('Content-Type', 'application/json'), auth_header]
            response = client.post(
                path,
                data=json.dumps(data),
                headers=headers)
            assert response.status_code == 201

            app.celery.tasks.process_job.apply_async.assert_called_once_with(
                ([str(job_id)]),
                queue="process-job"
            )

            resp_json = json.loads(response.get_data(as_text=True))

            assert resp_json['data']['id'] == str(job_id)
            assert resp_json['data']['service'] == str(sample_template.service.id)
            assert resp_json['data']['template'] == sample_template.id
            assert resp_json['data']['original_file_name'] == 'thisisatest.csv'


def test_create_job_returns_400_if_missing_data(notify_api, sample_template, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.process_job.apply_async')
            data = {
            }
            path = '/service/{}/job'.format(sample_template.service.id)
            auth_header = create_authorization_header(
                service_id=sample_template.service.id,
                path=path,
                method='POST',
                request_body=json.dumps(data))
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
            assert 'Missing data for required field.' in resp_json['message']['file_name']
            assert 'Missing data for required field.' in resp_json['message']['notification_count']
            assert 'Missing data for required field.' in resp_json['message']['id']
            assert 'Missing data for required field.' in resp_json['message']['bucket_name']


def test_create_job_returns_404_if_missing_service(notify_api, sample_template, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.process_job.apply_async')
            random_id = str(uuid.uuid4())
            data = {}
            path = '/service/{}/job'.format(random_id)
            auth_header = create_authorization_header(
                service_id=sample_template.service.id,
                path=path,
                method='POST',
                request_body=json.dumps(data))
            headers = [('Content-Type', 'application/json'), auth_header]
            response = client.post(
                path,
                data=json.dumps(data),
                headers=headers)

            resp_json = json.loads(response.get_data(as_text=True))
            assert response.status_code == 404

            app.celery.tasks.process_job.apply_async.assert_not_called()
            assert resp_json['result'] == 'error'
            assert resp_json['message'] == 'Service {} not found'.format(random_id)


def test_get_update_job(notify_api, sample_job):
    assert sample_job.status == 'pending'

    job_id = str(sample_job.id)
    service_id = str(sample_job.service.id)

    update_data = {
        'status': 'in progress'
    }

    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            path = '/service/{}/job/{}'.format(service_id, job_id)

            auth_header = create_authorization_header(
                service_id=service_id,
                path=path,
                method='POST',
                request_body=json.dumps(update_data))

            headers = [('Content-Type', 'application/json'), auth_header]

            response = client.post(path, headers=headers, data=json.dumps(update_data))

            resp_json = json.loads(response.get_data(as_text=True))
            assert response.status_code == 200
            assert resp_json['data']['status'] == 'in progress'


def _setup_jobs(notify_db, notify_db_session, template, number_of_jobs=5):
    for i in range(number_of_jobs):
        create_job(
            notify_db,
            notify_db_session,
            service=template.service,
            template=template)
