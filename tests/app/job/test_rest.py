import json
import uuid
from datetime import datetime, timedelta
from functools import partial

from freezegun import freeze_time
import pytest
import pytz
import app.celery.tasks

from tests import create_authorization_header
from tests.conftest import set_config
from tests.app.conftest import (
    sample_job as create_job,
    sample_notification as create_notification
)
from app.dao.templates_dao import dao_update_template
from app.models import NOTIFICATION_STATUS_TYPES, JOB_STATUS_TYPES, JOB_STATUS_PENDING


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
    print(response.get_data(as_text=True))
    resp_json = json.loads(response.get_data(as_text=True))
    print(resp_json)
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


def _setup_jobs(notify_db, notify_db_session, template, number_of_jobs=5):
    for i in range(number_of_jobs):
        create_job(
            notify_db,
            notify_db_session,
            service=template.service,
            template=template)


def test_get_all_notifications_for_job_in_order_of_job_number(
    client, notify_db, notify_db_session, sample_service
):
    main_job = create_job(notify_db, notify_db_session, service=sample_service)
    another_job = create_job(notify_db, notify_db_session, service=sample_service)

    notification_1 = create_notification(
        notify_db,
        notify_db_session,
        job=main_job,
        to_field="1",
        created_at=datetime.utcnow(),
        job_row_number=1
    )
    notification_2 = create_notification(
        notify_db,
        notify_db_session,
        job=main_job,
        to_field="2",
        created_at=datetime.utcnow(),
        job_row_number=2
    )
    notification_3 = create_notification(
        notify_db,
        notify_db_session,
        job=main_job,
        to_field="3",
        created_at=datetime.utcnow(),
        job_row_number=3
    )
    create_notification(notify_db, notify_db_session, job=another_job)

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
        (1, '?status={}'.format(NOTIFICATION_STATUS_TYPES[0])),
        (0, '?status={}'.format(NOTIFICATION_STATUS_TYPES[1])),
        (1, '?status={}&status={}&status={}'.format(*NOTIFICATION_STATUS_TYPES[0:3])),
        (0, '?status={}&status={}&status={}'.format(*NOTIFICATION_STATUS_TYPES[3:6])),
    ]
)
def test_get_all_notifications_for_job_filtered_by_status(
        client,
        notify_db,
        notify_db_session,
        sample_service,
        expected_notification_count,
        status_args
):
    job = create_job(notify_db, notify_db_session, service=sample_service)

    create_notification(
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


def test_get_all_notifications_for_job_returns_correct_format(
    client,
    sample_notification_with_job
):
    service_id = sample_notification_with_job.service_id
    job_id = sample_notification_with_job.job_id
    response = client.get(
        path='/service/{}/job/{}/notifications'.format(service_id, job_id),
        headers=[create_authorization_header()]
    )
    assert response.status_code == 200
    resp = json.loads(response.get_data(as_text=True))
    assert len(resp['notifications']) == 1
    assert resp['notifications'][0]['id'] == str(sample_notification_with_job.id)
    assert resp['notifications'][0]['status'] == sample_notification_with_job.status


def test_get_job_by_id(notify_api, sample_job):
    job_id = str(sample_job.id)
    service_id = sample_job.service.id
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            path = '/service/{}/job/{}'.format(service_id, job_id)
            auth_header = create_authorization_header()
            response = client.get(path, headers=[auth_header])
            assert response.status_code == 200
            resp_json = json.loads(response.get_data(as_text=True))
            assert resp_json['data']['id'] == job_id
            assert resp_json['data']['statistics'] == []
            assert resp_json['data']['created_by']['name'] == 'Test User'


def test_get_job_by_id_should_return_statistics(client, notify_db, notify_db_session, notify_api, sample_job):
    job_id = str(sample_job.id)
    service_id = sample_job.service.id
    partial_notification = partial(
        create_notification, notify_db, notify_db_session, service=sample_job.service, job=sample_job
    )
    partial_notification(status='created')
    partial_notification(status='sending')
    partial_notification(status='delivered')
    partial_notification(status='pending')
    partial_notification(status='failed')
    partial_notification(status='technical-failure')  # noqa
    partial_notification(status='temporary-failure')  # noqa
    partial_notification(status='permanent-failure')  # noqa

    path = '/service/{}/job/{}'.format(service_id, job_id)
    auth_header = create_authorization_header()
    response = client.get(path, headers=[auth_header])
    assert response.status_code == 200
    resp_json = json.loads(response.get_data(as_text=True))
    assert resp_json['data']['id'] == job_id
    assert {'status': 'created', 'count': 1} in resp_json['data']['statistics']
    assert {'status': 'sending', 'count': 1} in resp_json['data']['statistics']
    assert {'status': 'delivered', 'count': 1} in resp_json['data']['statistics']
    assert {'status': 'pending', 'count': 1} in resp_json['data']['statistics']
    assert {'status': 'failed', 'count': 1} in resp_json['data']['statistics']
    assert {'status': 'technical-failure', 'count': 1} in resp_json['data']['statistics']
    assert {'status': 'temporary-failure', 'count': 1} in resp_json['data']['statistics']
    assert {'status': 'permanent-failure', 'count': 1} in resp_json['data']['statistics']
    assert resp_json['data']['created_by']['name'] == 'Test User'


def test_get_job_by_id_should_return_summed_statistics(client, notify_db, notify_db_session, notify_api, sample_job):
    job_id = str(sample_job.id)
    service_id = sample_job.service.id
    partial_notification = partial(
        create_notification, notify_db, notify_db_session, service=sample_job.service, job=sample_job
    )
    partial_notification(status='created')
    partial_notification(status='created')
    partial_notification(status='created')
    partial_notification(status='sending')
    partial_notification(status='failed')
    partial_notification(status='failed')
    partial_notification(status='failed')
    partial_notification(status='technical-failure')
    partial_notification(status='temporary-failure')
    partial_notification(status='temporary-failure')

    path = '/service/{}/job/{}'.format(service_id, job_id)
    auth_header = create_authorization_header()
    response = client.get(path, headers=[auth_header])
    assert response.status_code == 200
    resp_json = json.loads(response.get_data(as_text=True))
    assert resp_json['data']['id'] == job_id
    assert {'status': 'created', 'count': 3} in resp_json['data']['statistics']
    assert {'status': 'sending', 'count': 1} in resp_json['data']['statistics']
    assert {'status': 'failed', 'count': 3} in resp_json['data']['statistics']
    assert {'status': 'technical-failure', 'count': 1} in resp_json['data']['statistics']
    assert {'status': 'temporary-failure', 'count': 2} in resp_json['data']['statistics']
    assert resp_json['data']['created_by']['name'] == 'Test User'


def test_get_jobs(client, notify_db, notify_db_session, sample_template):
    _setup_jobs(notify_db, notify_db_session, sample_template)

    service_id = sample_template.service.id

    path = '/service/{}/job'.format(service_id)
    auth_header = create_authorization_header()
    response = client.get(path, headers=[auth_header])
    assert response.status_code == 200
    resp_json = json.loads(response.get_data(as_text=True))
    assert len(resp_json['data']) == 5


def test_get_jobs_with_limit_days(admin_request, notify_db, notify_db_session, sample_template):
    for time in [
        'Sunday 1st July 2018 22:59',
        'Sunday 2nd July 2018 23:00',  # beginning of monday morning
        'Monday 3rd July 2018 12:00'
    ]:
        with freeze_time(time):
            create_job(
                notify_db,
                notify_db_session,
                service=sample_template.service,
                template=sample_template,
            )

    with freeze_time('Monday 9th July 2018 12:00'):
        resp_json = admin_request.get('job.get_jobs_by_service', service_id=sample_template.service_id, limit_days=7)

    assert len(resp_json['data']) == 2


def test_get_jobs_should_return_statistics(client, notify_db, notify_db_session, notify_api, sample_service):
    now = datetime.utcnow()
    earlier = datetime.utcnow() - timedelta(days=1)
    job_1 = create_job(notify_db, notify_db_session, service=sample_service, created_at=earlier)
    job_2 = create_job(notify_db, notify_db_session, service=sample_service, created_at=now)
    partial_notification = partial(create_notification, notify_db, notify_db_session, service=sample_service)
    partial_notification(job=job_1, status='created')
    partial_notification(job=job_1, status='created')
    partial_notification(job=job_1, status='created')
    partial_notification(job=job_2, status='sending')
    partial_notification(job=job_2, status='sending')
    partial_notification(job=job_2, status='sending')

    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            path = '/service/{}/job'.format(sample_service.id)
            auth_header = create_authorization_header()
            response = client.get(path, headers=[auth_header])
            assert response.status_code == 200
            resp_json = json.loads(response.get_data(as_text=True))
            assert len(resp_json['data']) == 2
            assert resp_json['data'][0]['id'] == str(job_2.id)
            assert {'status': 'sending', 'count': 3} in resp_json['data'][0]['statistics']
            assert resp_json['data'][1]['id'] == str(job_1.id)
            assert {'status': 'created', 'count': 3} in resp_json['data'][1]['statistics']


def test_get_jobs_should_return_no_stats_if_no_rows_in_notifications(
    client,
    notify_db,
    notify_db_session,
    notify_api,
    sample_service,
):

    now = datetime.utcnow()
    earlier = datetime.utcnow() - timedelta(days=1)
    job_1 = create_job(notify_db, notify_db_session, service=sample_service, created_at=earlier)
    job_2 = create_job(notify_db, notify_db_session, service=sample_service, created_at=now)

    path = '/service/{}/job'.format(sample_service.id)
    auth_header = create_authorization_header()
    response = client.get(path, headers=[auth_header])
    assert response.status_code == 200
    resp_json = json.loads(response.get_data(as_text=True))
    assert len(resp_json['data']) == 2
    assert resp_json['data'][0]['id'] == str(job_2.id)
    assert resp_json['data'][0]['statistics'] == []
    assert resp_json['data'][1]['id'] == str(job_1.id)
    assert resp_json['data'][1]['statistics'] == []


def test_get_jobs_should_paginate(
    notify_db,
    notify_db_session,
    client,
    sample_template
):
    create_10_jobs(notify_db, notify_db_session, sample_template.service, sample_template)

    path = '/service/{}/job'.format(sample_template.service_id)
    auth_header = create_authorization_header()

    with set_config(client.application, 'PAGE_SIZE', 2):
        response = client.get(path, headers=[auth_header])

    assert response.status_code == 200
    resp_json = json.loads(response.get_data(as_text=True))
    assert len(resp_json['data']) == 2
    assert resp_json['data'][0]['created_at'] == '2015-01-01T10:00:00+00:00'
    assert resp_json['data'][1]['created_at'] == '2015-01-01T09:00:00+00:00'
    assert resp_json['page_size'] == 2
    assert resp_json['total'] == 10
    assert 'links' in resp_json
    assert set(resp_json['links'].keys()) == {'next', 'last'}


def test_get_jobs_accepts_page_parameter(
    notify_db,
    notify_db_session,
    client,
    sample_template
):
    create_10_jobs(notify_db, notify_db_session, sample_template.service, sample_template)

    path = '/service/{}/job'.format(sample_template.service_id)
    auth_header = create_authorization_header()

    with set_config(client.application, 'PAGE_SIZE', 2):
        response = client.get(path, headers=[auth_header], query_string={'page': 2})

    assert response.status_code == 200
    resp_json = json.loads(response.get_data(as_text=True))
    assert len(resp_json['data']) == 2
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
def test_get_jobs_can_filter_on_statuses(
    notify_db,
    notify_db_session,
    client,
    sample_service,
    statuses_filter,
    expected_statuses
):
    create_job(notify_db, notify_db_session, job_status='pending')
    create_job(notify_db, notify_db_session, job_status='in progress')
    create_job(notify_db, notify_db_session, job_status='finished')
    create_job(notify_db, notify_db_session, job_status='sending limits exceeded')
    create_job(notify_db, notify_db_session, job_status='scheduled')
    create_job(notify_db, notify_db_session, job_status='cancelled')
    create_job(notify_db, notify_db_session, job_status='ready to send')
    create_job(notify_db, notify_db_session, job_status='sent to dvla')
    create_job(notify_db, notify_db_session, job_status='error')

    path = '/service/{}/job'.format(sample_service.id)
    response = client.get(
        path,
        headers=[create_authorization_header()],
        query_string={'statuses': statuses_filter}
    )

    assert response.status_code == 200
    resp_json = json.loads(response.get_data(as_text=True))
    from pprint import pprint
    pprint(resp_json)
    assert {x['job_status'] for x in resp_json['data']} == set(expected_statuses)


def create_10_jobs(db, session, service, template):
    with freeze_time('2015-01-01T00:00:00') as the_time:
        for _ in range(10):
            the_time.tick(timedelta(hours=1))
            create_job(db, session, service, template)


def test_get_all_notifications_for_job_returns_csv_format(
    client,
    notify_db,
    notify_db_session,
):
    job = create_job(notify_db, notify_db_session)
    notification = create_notification(
        notify_db,
        notify_db_session,
        job=job,
        job_row_number=1,
        created_at=datetime.utcnow(),
    )

    path = '/service/{}/job/{}/notifications'.format(notification.service.id, job.id)

    response = client.get(
        path=path,
        headers=[create_authorization_header()],
        query_string={'format_for_csv': True}
    )
    assert response.status_code == 200

    resp = json.loads(response.get_data(as_text=True))
    assert len(resp['notifications']) == 1
    notification = resp['notifications'][0]
    assert set(notification.keys()) == \
        set(['created_at', 'created_by_name', 'template_type',
             'template_name', 'job_name', 'status', 'row_number', 'recipient'])
