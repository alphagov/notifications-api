from flask import json

from app.variables import LETTER_TEST_API_FILENAME

from tests import create_authorization_header
from tests.app.db import create_job


def test_send_letter_jobs(client, mocker, sample_letter_template):
    mock_celery = mocker.patch("app.letters.rest.notify_celery.send_task")
    job_1 = create_job(sample_letter_template)
    job_2 = create_job(sample_letter_template)
    job_3 = create_job(sample_letter_template)
    job_ids = {"job_ids": [str(job_1.id), str(job_2.id), str(job_3.id)]}

    auth_header = create_authorization_header()

    response = client.post(
        path='/send-letter-jobs',
        data=json.dumps(job_ids),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 201
    assert json.loads(response.get_data())['data'] == {'response': "Task created to send files to DVLA"}

    mock_celery.assert_called_once_with(name="send-jobs-to-dvla",
                                        args=(job_ids['job_ids'],),
                                        queue="process-ftp-tasks")


def test_send_letter_jobs_throws_validation_error(client, mocker):
    mock_celery = mocker.patch("app.letters.rest.notify_celery.send_task")

    job_ids = {"job_ids": ["1", "2"]}

    auth_header = create_authorization_header()

    response = client.post(
        path='/send-letter-jobs',
        data=json.dumps(job_ids),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 400

    assert not mock_celery.called


def test_get_letter_jobs_excludes_non_letter_jobs(client, sample_letter_job, sample_job):
    auth_header = create_authorization_header()
    response = client.get(
        path='/letter-jobs',
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))
    assert len(json_resp['data']) == 1
    assert json_resp['data'][0]['id'] == str(sample_letter_job.id)
    assert json_resp['data'][0]['service_name']['name'] == sample_letter_job.service.name
    assert json_resp['data'][0]['job_status'] == 'pending'


def test_get_letter_jobs_excludes_test_jobs(admin_request, sample_letter_job):
    sample_letter_job.original_file_name = LETTER_TEST_API_FILENAME

    json_resp = admin_request.get('letter-job.get_letter_jobs')

    assert len(json_resp['data']) == 0
