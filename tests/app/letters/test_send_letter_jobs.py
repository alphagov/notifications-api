import uuid

from flask import current_app
from flask import json

from tests import create_authorization_header


def test_send_letter_jobs(client, mocker):
    mock_celery = mocker.patch("app.letters.send_letter_jobs.notify_celery.send_task")
    job_ids = {"job_ids": [str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())]}

    auth_header = create_authorization_header()

    response = client.post(
        path='/send-letter-jobs',
        data=json.dumps(job_ids),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 200
    assert response.get_data(as_text=True) == "Task created to send files to DVLA"

    mock_celery.assert_called_once_with(name="send-files-to-dvla",
                                        args=(job_ids['job_ids'],),
                                        queue="process-ftp")


def test_send_letter_jobs_throws_validation_error(client, mocker):
    mock_celery = mocker.patch("app.letters.send_letter_jobs.notify_celery.send_task")

    job_ids = {"job_ids": ["1", "2"]}

    auth_header = create_authorization_header()

    response = client.post(
        path='/send-letter-jobs',
        data=json.dumps(job_ids),
        headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 400

    assert not mock_celery.called
