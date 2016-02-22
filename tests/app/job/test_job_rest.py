import boto3
import moto
import json
import uuid
from flask import url_for

from tests import create_authorization_header
from tests.app.conftest import sample_job as create_job


def test_get_jobs(notify_api, notify_db, notify_db_session, sample_template):
    _setup_jobs(notify_db, notify_db_session, sample_template)

    service_id = sample_template.service.id

    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            path = url_for('job.get_job_for_service', service_id=service_id)
            auth_header = create_authorization_header(service_id=service_id,
                                                      path=path,
                                                      method='GET')
            response = client.get(path, headers=[auth_header])
            assert response.status_code == 200
            resp_json = json.loads(response.get_data(as_text=True))
            assert len(resp_json['data']) == 5


def test_get_job_with_invalid_id_returns400(notify_api, notify_db,
                                            notify_db_session,
                                            sample_template):
    service_id = sample_template.service.id
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            path = url_for('job.get_job_for_service', job_id='invalid_id', service_id=service_id)
            auth_header = create_authorization_header(service_id=sample_template.service.id,
                                                      path=path,
                                                      method='GET')
            response = client.get(path, headers=[auth_header])
            assert response.status_code == 400
            resp_json = json.loads(response.get_data(as_text=True))
            assert resp_json == {'message': 'Invalid job id',
                                 'result': 'error'}


def test_get_job_with_unknown_id_returns404(notify_api, notify_db,
                                            notify_db_session,
                                            sample_template):
    random_id = str(uuid.uuid4())
    service_id = sample_template.service.id
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            path = url_for('job.get_job_for_service', job_id=random_id, service_id=service_id)
            auth_header = create_authorization_header(service_id=sample_template.service.id,
                                                      path=path,
                                                      method='GET')
            response = client.get(path, headers=[auth_header])
            assert response.status_code == 404
            resp_json = json.loads(response.get_data(as_text=True))
            assert resp_json == {'message': 'Job not found', 'result': 'error'}


def test_get_job_by_id(notify_api, notify_db, notify_db_session,
                       sample_job):
    job_id = str(sample_job.id)
    service_id = sample_job.service.id
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            path = url_for('job.get_job_for_service', job_id=job_id, service_id=service_id)
            auth_header = create_authorization_header(service_id=sample_job.service.id,
                                                      path=path,
                                                      method='GET')
            response = client.get(path, headers=[auth_header])
            assert response.status_code == 200
            resp_json = json.loads(response.get_data(as_text=True))
            assert resp_json['data']['id'] == job_id


@moto.mock_sqs
def test_create_job(notify_api, notify_db, notify_db_session, sample_template):
    job_id = uuid.uuid4()
    template_id = sample_template.id
    service_id = sample_template.service.id
    original_file_name = 'thisisatest.csv'
    bucket_name = 'service-{}-notify'.format(service_id)
    file_name = '{}.csv'.format(job_id)
    data = {
        'id': str(job_id),
        'service': str(service_id),
        'template': template_id,
        'original_file_name': original_file_name,
        'bucket_name': bucket_name,
        'file_name': file_name,
        'notification_count': 1
    }

    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            path = url_for('job.create_job', service_id=service_id)
            auth_header = create_authorization_header(service_id=sample_template.service.id,
                                                      path=path,
                                                      method='POST',
                                                      request_body=json.dumps(data))
            headers = [('Content-Type', 'application/json'), auth_header]
            response = client.post(
                path,
                data=json.dumps(data),
                headers=headers)
    assert response.status_code == 201

    resp_json = json.loads(response.get_data(as_text=True))

    assert resp_json['data']['id'] == str(job_id)
    assert resp_json['data']['service'] == str(service_id)
    assert resp_json['data']['template'] == template_id
    assert resp_json['data']['original_file_name'] == original_file_name

    boto3.setup_default_session(region_name='eu-west-1')
    q = boto3.resource('sqs').get_queue_by_name(QueueName=notify_api.config['NOTIFY_JOB_QUEUE'])
    messages = q.receive_messages()
    assert len(messages) == 1

    expected_message = json.loads(messages[0].body)
    assert expected_message['id'] == str(job_id)
    assert expected_message['service'] == str(service_id)
    assert expected_message['template'] == template_id
    assert expected_message['bucket_name'] == bucket_name


def test_get_update_job_status(notify_api,
                               notify_db,
                               notify_db_session,
                               sample_job):

    assert sample_job.status == 'pending'

    job_id = str(sample_job.id)
    service_id = str(sample_job.service.id)

    update_data = {
        'id': job_id,
        'service': service_id,
        'template': sample_job.template.id,
        'bucket_name': sample_job.bucket_name,
        'file_name': sample_job.file_name,
        'original_file_name': sample_job.original_file_name,
        'status': 'in progress',
        'notification_count': 1
    }

    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            path = url_for('job.update_job', service_id=service_id, job_id=job_id)

            auth_header = create_authorization_header(service_id=service_id,
                                                      path=path,
                                                      method='PUT',
                                                      request_body=json.dumps(update_data))

            headers = [('Content-Type', 'application/json'), auth_header]

            response = client.put(path, headers=headers, data=json.dumps(update_data))

            assert response.status_code == 200
            resp_json = json.loads(response.get_data(as_text=True))
            assert resp_json['data']['status'] == 'in progress'


def test_get_notification(notify_api, notify_db, notify_db_session, sample_notification):

    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            path = url_for('job.get_notification_for_job',
                           service_id=sample_notification.service.id,
                           job_id=sample_notification.job.id,
                           notification_id=sample_notification.id)

            auth_header = create_authorization_header(service_id=sample_notification.service.id,
                                                      path=path,
                                                      method='GET')

            headers = [('Content-Type', 'application/json'), auth_header]
            response = client.get(path, headers=headers)
            resp_json = json.loads(response.get_data(as_text=True))

            assert str(sample_notification.id) == resp_json['data']['id']
            assert str(sample_notification.service.id) == resp_json['data']['service']
            assert sample_notification.template.id == resp_json['data']['template']
            assert str(sample_notification.job.id) == resp_json['data']['job']
            assert sample_notification.status == resp_json['data']['status']


def test_get_notifications(notify_api, notify_db, notify_db_session, sample_job):

    from tests.app.conftest import sample_notification
    for i in range(0, 5):
        sample_notification(notify_db,
                            notify_db_session,
                            service=sample_job.service,
                            template=sample_job.template,
                            job=sample_job)

    service_id = str(sample_job.service.id)
    job_id = str(sample_job.id)

    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            path = url_for('job.get_notification_for_job',
                           service_id=service_id,
                           job_id=job_id)

            auth_header = create_authorization_header(service_id=service_id,
                                                      path=path,
                                                      method='GET')

            headers = [('Content-Type', 'application/json'), auth_header]
            response = client.get(path, headers=headers)
            resp_json = json.loads(response.get_data(as_text=True))

            assert len(resp_json['data']) == 5


def test_add_notification(notify_api, notify_db, notify_db_session, sample_job):

    to = '+44709123456'
    data = {
        'to': to,
        'job': str(sample_job.id),
        'service': str(sample_job.service.id),
        'template': sample_job.template.id
    }
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            path = url_for('job.create_notification_for_job',
                           service_id=sample_job.service.id,
                           job_id=sample_job.id)

            auth_header = create_authorization_header(service_id=sample_job.service.id,
                                                      path=path,
                                                      method='POST',
                                                      request_body=json.dumps(data))

            headers = [('Content-Type', 'application/json'), auth_header]

            response = client.post(path, headers=headers, data=json.dumps(data))

            resp_json = json.loads(response.get_data(as_text=True))

            assert resp_json['data']['id']
            assert data['to'] == resp_json['data']['to']
            assert data['service'] == resp_json['data']['service']
            assert data['template'] == resp_json['data']['template']
            assert data['job'] == resp_json['data']['job']
            assert 'sent' == resp_json['data']['status']


def test_add_notification_with_id(notify_api, notify_db, notify_db_session, sample_job):
    notification_id = str(uuid.uuid4())
    to = '+44709123456'
    data = {
        'id': notification_id,
        'to': to,
        'job': str(sample_job.id),
        'service': str(sample_job.service.id),
        'template': sample_job.template.id
    }
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            path = url_for('job.create_notification_for_job',
                           service_id=sample_job.service.id,
                           job_id=sample_job.id)

            auth_header = create_authorization_header(service_id=sample_job.service.id,
                                                      path=path,
                                                      method='POST',
                                                      request_body=json.dumps(data))

            headers = [('Content-Type', 'application/json'), auth_header]

            response = client.post(path, headers=headers, data=json.dumps(data))

            resp_json = json.loads(response.get_data(as_text=True))

            assert resp_json['data']['id'] == notification_id
            assert data['to'] == resp_json['data']['to']
            assert data['service'] == resp_json['data']['service']
            assert data['template'] == resp_json['data']['template']
            assert data['job'] == resp_json['data']['job']
            assert 'sent' == resp_json['data']['status']


def test_update_notification(notify_api, notify_db, notify_db_session, sample_notification):

    assert sample_notification.status == 'sent'

    update_data = {
        'id': str(sample_notification.id),
        'to': sample_notification.to,
        'job': str(sample_notification.job.id),
        'service': str(sample_notification.service.id),
        'template': sample_notification.template.id,
        'status': 'failed'
    }
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            path = url_for('job.update_notification_for_job',
                           service_id=sample_notification.service.id,
                           job_id=sample_notification.job.id,
                           notification_id=sample_notification.id)

            auth_header = create_authorization_header(service_id=sample_notification.service.id,
                                                      path=path,
                                                      method='PUT',
                                                      request_body=json.dumps(update_data))

            headers = [('Content-Type', 'application/json'), auth_header]

            response = client.put(path, headers=headers, data=json.dumps(update_data))

            resp_json = json.loads(response.get_data(as_text=True))

            assert update_data['id'] == resp_json['data']['id']
            assert 'failed' == resp_json['data']['status']


def _setup_jobs(notify_db, notify_db_session, template, number_of_jobs=5):
    for i in range(number_of_jobs):
        create_job(notify_db, notify_db_session, service=template.service,
                   template=template)
