import json
import uuid
from datetime import datetime, timedelta

from freezegun import freeze_time
import pytest
import pytz

import app.celery.tasks
from app.dao.templates_dao import dao_update_template
from app.models import JOB_STATUS_TYPES, JOB_STATUS_PENDING

from tests import create_authorization_header
from tests.conftest import set_config
from tests.app.db import create_job, create_notification


def test_get_job_with_invalid_service_id_returns404(client, sample_service):
    path = '/service/{}/job'.format(sample_service.id)
    auth_header = create_authorization_header()
    response = client.get(path, headers=[auth_header])
    assert response.status_code == 200
    resp_json = json.loads(response.get_data(as_text=True))
    assert len(resp_json['data']) == 0


def test_get_job_with_invalid_job_id_returns404(client, sample_template):
    service_id = sample_template.service.id
    path = '/service/{}/job/{}'.format(service_id, "bad-id")
    auth_header = create_authorization_header()
    response = client.get(path, headers=[auth_header])
    assert response.status_code == 404
    resp_json = json.loads(response.get_data(as_text=True))
    assert resp_json['result'] == 'error'
    assert resp_json['message'] == 'No result found'


def test_get_job_with_unknown_id_returns404(client, sample_template, fake_uuid):
    service_id = sample_template.service.id
    path = '/service/{}/job/{}'.format(service_id, fake_uuid)
    auth_header = create_authorization_header()
    response = client.get(path, headers=[auth_header])
    assert response.status_code == 404
    resp_json = json.loads(response.get_data(as_text=True))
    assert resp_json == {
        'message': 'No result found',
        'result': 'error'
    }


def test_cancel_job(client, sample_scheduled_job):
    job_id = str(sample_scheduled_job.id)
    service_id = sample_scheduled_job.service.id
    path = '/service/{}/job/{}/cancel'.format(service_id, job_id)
    auth_header = create_authorization_header()
    response = client.post(path, headers=[auth_header])
    assert response.status_code == 200
    resp_json = json.loads(response.get_data(as_text=True))
    assert resp_json['data']['id'] == job_id
    assert resp_json['data']['job_status'] == 'cancelled'


def test_cant_cancel_normal_job(client, sample_job, mocker):
    job_id = str(sample_job.id)
    service_id = sample_job.service.id
    mock_update = mocker.patch('app.dao.jobs_dao.dao_update_job')
    path = '/service/{}/job/{}/cancel'.format(service_id, job_id)
    auth_header = create_authorization_header()
    response = client.post(path, headers=[auth_header])
    assert response.status_code == 404
    assert mock_update.call_count == 0


def test_create_unscheduled_job(client, sample_template, mocker, fake_uuid):
    mocker.patch('app.celery.tasks.process_job.apply_async')
    mocker.patch('app.job.rest.get_job_metadata_from_s3', return_value={
        'template_id': str(sample_template.id),
        'original_file_name': 'thisisatest.csv',
        'notification_count': '1',
        'valid': 'True',
    })
    data = {
        'id': fake_uuid,
        'created_by': str(sample_template.created_by.id),
    }
    path = '/service/{}/job'.format(sample_template.service.id)
    auth_header = create_authorization_header()
    headers = [('Content-Type', 'application/json'), auth_header]

    response = client.post(
        path,
        data=json.dumps(data),
        headers=headers)
    assert response.status_code == 201

    app.celery.tasks.process_job.apply_async.assert_called_once_with(
        ([str(fake_uuid)]),
        {'sender_id': None},
        queue="job-tasks"
    )

    resp_json = json.loads(response.get_data(as_text=True))

    assert resp_json['data']['id'] == fake_uuid
    assert resp_json['data']['statistics'] == []
    assert resp_json['data']['job_status'] == 'pending'
    assert not resp_json['data']['scheduled_for']
    assert resp_json['data']['job_status'] == 'pending'
    assert resp_json['data']['template'] == str(sample_template.id)
    assert resp_json['data']['original_file_name'] == 'thisisatest.csv'
    assert resp_json['data']['notification_count'] == 1


def test_create_unscheduled_job_with_sender_id_in_metadata(client, sample_template, mocker, fake_uuid):
    mocker.patch('app.celery.tasks.process_job.apply_async')
    mocker.patch('app.job.rest.get_job_metadata_from_s3', return_value={
        'template_id': str(sample_template.id),
        'original_file_name': 'thisisatest.csv',
        'notification_count': '1',
        'valid': 'True',
        'sender_id': fake_uuid
    })
    data = {
        'id': fake_uuid,
        'created_by': str(sample_template.created_by.id),
    }
    path = '/service/{}/job'.format(sample_template.service.id)
    auth_header = create_authorization_header()
    headers = [('Content-Type', 'application/json'), auth_header]

    response = client.post(
        path,
        data=json.dumps(data),
        headers=headers)
    assert response.status_code == 201

    app.celery.tasks.process_job.apply_async.assert_called_once_with(
        ([str(fake_uuid)]),
        {'sender_id': fake_uuid},
        queue="job-tasks"
    )


@freeze_time("2016-01-01 12:00:00.000000")
def test_create_scheduled_job(client, sample_template, mocker, fake_uuid):
    scheduled_date = (datetime.utcnow() + timedelta(hours=95, minutes=59)).isoformat()
    mocker.patch('app.celery.tasks.process_job.apply_async')
    mocker.patch('app.job.rest.get_job_metadata_from_s3', return_value={
        'template_id': str(sample_template.id),
        'original_file_name': 'thisisatest.csv',
        'notification_count': '1',
        'valid': 'True',
    })
    data = {
        'id': fake_uuid,
        'created_by': str(sample_template.created_by.id),
        'scheduled_for': scheduled_date,
    }
    path = '/service/{}/job'.format(sample_template.service.id)
    auth_header = create_authorization_header()
    headers = [('Content-Type', 'application/json'), auth_header]

    response = client.post(
        path,
        data=json.dumps(data),
        headers=headers)
    assert response.status_code == 201

    app.celery.tasks.process_job.apply_async.assert_not_called()

    resp_json = json.loads(response.get_data(as_text=True))

    assert resp_json['data']['id'] == fake_uuid
    assert resp_json['data']['scheduled_for'] == datetime(2016, 1, 5, 11, 59, 0,
                                                          tzinfo=pytz.UTC).isoformat()
    assert resp_json['data']['job_status'] == 'scheduled'
    assert resp_json['data']['template'] == str(sample_template.id)
    assert resp_json['data']['original_file_name'] == 'thisisatest.csv'
    assert resp_json['data']['notification_count'] == 1


def test_create_job_returns_403_if_service_is_not_active(client, fake_uuid, sample_service, mocker):
    sample_service.active = False
    mock_job_dao = mocker.patch("app.dao.jobs_dao.dao_create_job")
    auth_header = create_authorization_header()
    response = client.post('/service/{}/job'.format(sample_service.id),
                           data="",
                           headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 403
    resp_json = json.loads(response.get_data(as_text=True))
    assert resp_json['result'] == 'error'
    assert resp_json['message'] == "Create job is not allowed: service is inactive "
    mock_job_dao.assert_not_called()


@pytest.mark.parametrize('extra_metadata', (
    {},
    {'valid': 'anything not the string True'},
))
def test_create_job_returns_400_if_file_is_invalid(
    client,
    fake_uuid,
    sample_template,
    mocker,
    extra_metadata,
):
    mock_job_dao = mocker.patch("app.dao.jobs_dao.dao_create_job")
    auth_header = create_authorization_header()
    metadata = dict(
        template_id=str(sample_template.id),
        original_file_name='thisisatest.csv',
        notification_count=1,
        **extra_metadata
    )
    mocker.patch('app.job.rest.get_job_metadata_from_s3', return_value=metadata)
    data = {'id': fake_uuid}
    response = client.post(
        '/service/{}/job'.format(sample_template.service.id),
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header]
    )

    assert response.status_code == 400
    resp_json = json.loads(response.get_data(as_text=True))
    assert resp_json['result'] == 'error'
    assert resp_json['message'] == 'File is not valid, can\'t create job'
    mock_job_dao.assert_not_called()


def test_create_job_returns_403_if_letter_template_type_and_service_in_trial(
    client, fake_uuid, sample_trial_letter_template, mocker
):
    mocker.patch('app.job.rest.get_job_metadata_from_s3', return_value={
        'template_id': str(sample_trial_letter_template.id),
        'original_file_name': 'thisisatest.csv',
        'notification_count': '1',
    })
    data = {
        'id': fake_uuid,
        'created_by': str(sample_trial_letter_template.created_by.id),
    }
    mock_job_dao = mocker.patch("app.dao.jobs_dao.dao_create_job")
    auth_header = create_authorization_header()
    response = client.post('/service/{}/job'.format(sample_trial_letter_template.service.id),
                           data=json.dumps(data),
                           headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 403
    resp_json = json.loads(response.get_data(as_text=True))
    assert resp_json['result'] == 'error'
    assert resp_json['message'] == "Create letter job is not allowed for service in trial mode "
    mock_job_dao.assert_not_called()


@freeze_time("2016-01-01 11:09:00.061258")
def test_should_not_create_scheduled_job_more_then_24_hours_hence(client, sample_template, mocker, fake_uuid):
    scheduled_date = (datetime.utcnow() + timedelta(hours=96, minutes=1)).isoformat()
    mocker.patch('app.celery.tasks.process_job.apply_async')
    mocker.patch('app.job.rest.get_job_metadata_from_s3', return_value={
        'template_id': str(sample_template.id),
        'original_file_name': 'thisisatest.csv',
        'notification_count': '1',
        'valid': 'True',
    })
    data = {
        'id': fake_uuid,
        'created_by': str(sample_template.created_by.id),
        'scheduled_for': scheduled_date,
    }
    path = '/service/{}/job'.format(sample_template.service.id)
    auth_header = create_authorization_header()
    headers = [('Content-Type', 'application/json'), auth_header]

    response = client.post(
        path,
        data=json.dumps(data),
        headers=headers)
    assert response.status_code == 400

    app.celery.tasks.process_job.apply_async.assert_not_called()

    resp_json = json.loads(response.get_data(as_text=True))
    assert resp_json['result'] == 'error'
    assert 'scheduled_for' in resp_json['message']
    assert resp_json['message']['scheduled_for'] == ['Date cannot be more than 96hrs in the future']


@freeze_time("2016-01-01 11:09:00.061258")
def test_should_not_create_scheduled_job_in_the_past(client, sample_template, mocker, fake_uuid):
    scheduled_date = (datetime.utcnow() - timedelta(minutes=1)).isoformat()
    mocker.patch('app.celery.tasks.process_job.apply_async')
    mocker.patch('app.job.rest.get_job_metadata_from_s3', return_value={
        'template_id': str(sample_template.id),
        'original_file_name': 'thisisatest.csv',
        'notification_count': '1',
        'valid': 'True',
    })
    data = {
        'id': fake_uuid,
        'created_by': str(sample_template.created_by.id),
        'scheduled_for': scheduled_date
    }
    path = '/service/{}/job'.format(sample_template.service.id)
    auth_header = create_authorization_header()
    headers = [('Content-Type', 'application/json'), auth_header]

    response = client.post(
        path,
        data=json.dumps(data),
        headers=headers)
    assert response.status_code == 400

    app.celery.tasks.process_job.apply_async.assert_not_called()

    resp_json = json.loads(response.get_data(as_text=True))
    assert resp_json['result'] == 'error'
    assert 'scheduled_for' in resp_json['message']
    assert resp_json['message']['scheduled_for'] == ['Date cannot be in the past']


def test_create_job_returns_400_if_missing_id(client, sample_template, mocker):
    mocker.patch('app.celery.tasks.process_job.apply_async')
    mocker.patch('app.job.rest.get_job_metadata_from_s3', return_value={
        'template_id': str(sample_template.id),
    })
    data = {}
    path = '/service/{}/job'.format(sample_template.service.id)
    auth_header = create_authorization_header()
    headers = [('Content-Type', 'application/json'), auth_header]
    response = client.post(
        path,
        data=json.dumps(data),
        headers=headers)

    resp_json = json.loads(response.get_data(as_text=True))
    assert response.status_code == 400

    app.celery.tasks.process_job.apply_async.assert_not_called()
    assert resp_json['result'] == 'error'
    assert 'Missing data for required field.' in resp_json['message']['id']


def test_create_job_returns_400_if_missing_data(client, sample_template, mocker, fake_uuid):
    mocker.patch('app.celery.tasks.process_job.apply_async')
    mocker.patch('app.job.rest.get_job_metadata_from_s3', return_value={
        'template_id': str(sample_template.id),
    })
    data = {
        'id': fake_uuid,
        'valid': 'True',
    }
    path = '/service/{}/job'.format(sample_template.service.id)
    auth_header = create_authorization_header()
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


def test_create_job_returns_404_if_template_does_not_exist(client, sample_service, mocker, fake_uuid):
    mocker.patch('app.celery.tasks.process_job.apply_async')
    mocker.patch('app.job.rest.get_job_metadata_from_s3', return_value={
        'template_id': str(sample_service.id),
    })
    data = {
        'id': fake_uuid,
    }
    path = '/service/{}/job'.format(sample_service.id)
    auth_header = create_authorization_header()
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


def test_create_job_returns_404_if_missing_service(client, sample_template, mocker):
    mocker.patch('app.celery.tasks.process_job.apply_async')
    mocker.patch('app.job.rest.get_job_metadata_from_s3', return_value={
        'template_id': str(sample_template.id),
    })
    random_id = str(uuid.uuid4())
    data = {}
    path = '/service/{}/job'.format(random_id)
    auth_header = create_authorization_header()
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


def test_create_job_returns_400_if_archived_template(client, sample_template, mocker, fake_uuid):
    mocker.patch('app.celery.tasks.process_job.apply_async')
    sample_template.archived = True
    dao_update_template(sample_template)
    mocker.patch('app.job.rest.get_job_metadata_from_s3', return_value={
        'template_id': str(sample_template.id),
    })
    data = {
        'id': fake_uuid,
        'valid': 'True',
    }
    path = '/service/{}/job'.format(sample_template.service.id)
    auth_header = create_authorization_header()
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


def _setup_jobs(template, number_of_jobs=5):
    for i in range(number_of_jobs):
        create_job(template=template)


def test_get_all_notifications_for_job_in_order_of_job_number(admin_request, sample_template):
    main_job = create_job(sample_template)
    another_job = create_job(sample_template)

    notification_1 = create_notification(job=main_job, to_field="1", job_row_number=1)
    notification_2 = create_notification(job=main_job, to_field="2", job_row_number=2)
    notification_3 = create_notification(job=main_job, to_field="3", job_row_number=3)
    create_notification(job=another_job)

    resp = admin_request.get(
        'job.get_all_notifications_for_service_job',
        service_id=main_job.service_id,
        job_id=main_job.id
    )

    assert len(resp['notifications']) == 3
    assert resp['notifications'][0]['to'] == notification_1.to
    assert resp['notifications'][0]['job_row_number'] == notification_1.job_row_number
    assert resp['notifications'][1]['to'] == notification_2.to
    assert resp['notifications'][1]['job_row_number'] == notification_2.job_row_number
    assert resp['notifications'][2]['to'] == notification_3.to
    assert resp['notifications'][2]['job_row_number'] == notification_3.job_row_number


@pytest.mark.parametrize(
    "expected_notification_count, status_args",
    [
        (1, ['created']),
        (0, ['sending']),
        (1, ['created', 'sending']),
        (0, ['sending', 'delivered']),
    ]
)
def test_get_all_notifications_for_job_filtered_by_status(
        admin_request,
        sample_job,
        expected_notification_count,
        status_args
):
    create_notification(job=sample_job, to_field="1", status='created')

    resp = admin_request.get(
        'job.get_all_notifications_for_service_job',
        service_id=sample_job.service_id,
        job_id=sample_job.id,
        status=status_args
    )
    assert len(resp['notifications']) == expected_notification_count


def test_get_all_notifications_for_job_returns_correct_format(
    admin_request,
    sample_notification_with_job
):
    service_id = sample_notification_with_job.service_id
    job_id = sample_notification_with_job.job_id

    resp = admin_request.get('job.get_all_notifications_for_service_job', service_id=service_id, job_id=job_id)

    assert len(resp['notifications']) == 1
    assert resp['notifications'][0]['id'] == str(sample_notification_with_job.id)
    assert resp['notifications'][0]['status'] == sample_notification_with_job.status


def test_get_job_by_id(admin_request, sample_job):
    job_id = str(sample_job.id)
    service_id = sample_job.service.id

    resp_json = admin_request.get('job.get_job_by_service_and_job_id', service_id=service_id, job_id=job_id)

    assert resp_json['data']['id'] == job_id
    assert resp_json['data']['statistics'] == []
    assert resp_json['data']['created_by']['name'] == 'Test User'


def test_get_job_by_id_should_return_summed_statistics(admin_request, sample_job):
    job_id = str(sample_job.id)
    service_id = sample_job.service.id

    create_notification(job=sample_job, status='created')
    create_notification(job=sample_job, status='created')
    create_notification(job=sample_job, status='created')
    create_notification(job=sample_job, status='sending')
    create_notification(job=sample_job, status='failed')
    create_notification(job=sample_job, status='failed')
    create_notification(job=sample_job, status='failed')
    create_notification(job=sample_job, status='technical-failure')
    create_notification(job=sample_job, status='temporary-failure')
    create_notification(job=sample_job, status='temporary-failure')

    resp_json = admin_request.get('job.get_job_by_service_and_job_id', service_id=service_id, job_id=job_id)

    assert resp_json['data']['id'] == job_id
    assert {'status': 'created', 'count': 3} in resp_json['data']['statistics']
    assert {'status': 'sending', 'count': 1} in resp_json['data']['statistics']
    assert {'status': 'failed', 'count': 3} in resp_json['data']['statistics']
    assert {'status': 'technical-failure', 'count': 1} in resp_json['data']['statistics']
    assert {'status': 'temporary-failure', 'count': 2} in resp_json['data']['statistics']
    assert resp_json['data']['created_by']['name'] == 'Test User'


def test_get_jobs(admin_request, sample_template):
    _setup_jobs(sample_template)

    service_id = sample_template.service.id

    resp_json = admin_request.get('job.get_jobs_by_service', service_id=service_id)
    assert len(resp_json['data']) == 5


def test_get_jobs_with_limit_days(admin_request, sample_template):
    for time in [
        'Sunday 1st July 2018 22:59',
        'Sunday 2nd July 2018 23:00',  # beginning of monday morning
        'Monday 3rd July 2018 12:00'
    ]:
        with freeze_time(time):
            create_job(template=sample_template)

    with freeze_time('Monday 9th July 2018 12:00'):
        resp_json = admin_request.get('job.get_jobs_by_service', service_id=sample_template.service_id, limit_days=7)

    assert len(resp_json['data']) == 2


def test_get_jobs_should_return_statistics(admin_request, sample_template):
    now = datetime.utcnow()
    earlier = datetime.utcnow() - timedelta(days=1)
    job_1 = create_job(sample_template, created_at=earlier)
    job_2 = create_job(sample_template, created_at=now)
    create_notification(job=job_1, status='created')
    create_notification(job=job_1, status='created')
    create_notification(job=job_1, status='created')
    create_notification(job=job_2, status='sending')
    create_notification(job=job_2, status='sending')
    create_notification(job=job_2, status='sending')

    resp_json = admin_request.get('job.get_jobs_by_service', service_id=sample_template.service_id)

    assert len(resp_json['data']) == 2
    assert resp_json['data'][0]['id'] == str(job_2.id)
    assert {'status': 'sending', 'count': 3} in resp_json['data'][0]['statistics']
    assert resp_json['data'][1]['id'] == str(job_1.id)
    assert {'status': 'created', 'count': 3} in resp_json['data'][1]['statistics']


def test_get_jobs_should_return_no_stats_if_no_rows_in_notifications(admin_request, sample_template):
    now = datetime.utcnow()
    earlier = datetime.utcnow() - timedelta(days=1)
    job_1 = create_job(sample_template, created_at=earlier)
    job_2 = create_job(sample_template, created_at=now)

    resp_json = admin_request.get('job.get_jobs_by_service', service_id=sample_template.service_id)

    assert len(resp_json['data']) == 2
    assert resp_json['data'][0]['id'] == str(job_2.id)
    assert resp_json['data'][0]['statistics'] == []
    assert resp_json['data'][1]['id'] == str(job_1.id)
    assert resp_json['data'][1]['statistics'] == []


def test_get_jobs_should_paginate(admin_request, sample_template):
    create_10_jobs(sample_template)

    with set_config(admin_request.app, 'PAGE_SIZE', 2):
        resp_json = admin_request.get('job.get_jobs_by_service', service_id=sample_template.service_id)

    assert resp_json['data'][0]['created_at'] == '2015-01-01T10:00:00+00:00'
    assert resp_json['data'][1]['created_at'] == '2015-01-01T09:00:00+00:00'
    assert resp_json['page_size'] == 2
    assert resp_json['total'] == 10
    assert 'links' in resp_json
    assert set(resp_json['links'].keys()) == {'next', 'last'}


def test_get_jobs_accepts_page_parameter(admin_request, sample_template):
    create_10_jobs(sample_template)

    with set_config(admin_request.app, 'PAGE_SIZE', 2):
        resp_json = admin_request.get('job.get_jobs_by_service', service_id=sample_template.service_id, page=2)

    assert resp_json['data'][0]['created_at'] == '2015-01-01T08:00:00+00:00'
    assert resp_json['data'][1]['created_at'] == '2015-01-01T07:00:00+00:00'
    assert resp_json['page_size'] == 2
    assert resp_json['total'] == 10
    assert 'links' in resp_json
    assert set(resp_json['links'].keys()) == {'prev', 'next', 'last'}


@pytest.mark.parametrize('statuses_filter, expected_statuses', [
    ('', JOB_STATUS_TYPES),
    ('pending', [JOB_STATUS_PENDING]),
    ('pending, in progress, finished, sending limits exceeded, scheduled, cancelled, ready to send, sent to dvla, error',  # noqa
     JOB_STATUS_TYPES),
    # bad statuses are accepted, just return no data
    ('foo', [])
])
def test_get_jobs_can_filter_on_statuses(admin_request, sample_template, statuses_filter, expected_statuses):
    create_job(sample_template, job_status='pending')
    create_job(sample_template, job_status='in progress')
    create_job(sample_template, job_status='finished')
    create_job(sample_template, job_status='sending limits exceeded')
    create_job(sample_template, job_status='scheduled')
    create_job(sample_template, job_status='cancelled')
    create_job(sample_template, job_status='ready to send')
    create_job(sample_template, job_status='sent to dvla')
    create_job(sample_template, job_status='error')

    resp_json = admin_request.get(
        'job.get_jobs_by_service',
        service_id=sample_template.service_id,
        statuses=statuses_filter
    )

    assert {x['job_status'] for x in resp_json['data']} == set(expected_statuses)


def create_10_jobs(template):
    with freeze_time('2015-01-01T00:00:00') as the_time:
        for _ in range(10):
            the_time.tick(timedelta(hours=1))
            create_job(template)


def test_get_all_notifications_for_job_returns_csv_format(admin_request, sample_notification_with_job):
    resp = admin_request.get(
        'job.get_all_notifications_for_service_job',
        service_id=sample_notification_with_job.service_id,
        job_id=sample_notification_with_job.job_id,
        format_for_csv=True
    )

    assert len(resp['notifications']) == 1
    assert set(resp['notifications'][0].keys()) == {
        'created_at',
        'created_by_name',
        'created_by_email_address',
        'template_type',
        'template_name',
        'job_name',
        'status',
        'row_number',
        'recipient'
    }
