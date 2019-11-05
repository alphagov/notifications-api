from datetime import datetime, timedelta
from unittest.mock import call

import pytest
from freezegun import freeze_time
from mock import mock

from app import db
from app.celery import scheduled_tasks
from app.celery.scheduled_tasks import (
    check_job_status,
    delete_invitations,
    delete_verify_codes,
    run_scheduled_jobs,
    send_scheduled_notifications,
    switch_current_sms_provider_on_slow_delivery,
    replay_created_notifications,
    check_precompiled_letter_state,
    check_templated_letter_state,
    check_for_missing_rows_in_completed_jobs
)
from app.config import QueueNames, TaskNames
from app.dao.jobs_dao import dao_get_job_by_id
from app.dao.notifications_dao import dao_get_scheduled_notifications
from app.dao.provider_details_dao import (
    dao_update_provider_details,
    get_current_provider
)
from app.models import (
    JOB_STATUS_IN_PROGRESS,
    JOB_STATUS_ERROR,
    JOB_STATUS_FINISHED,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_PENDING_VIRUS_CHECK,
)
from app.v2.errors import JobIncompleteError
from tests.app import load_example_csv

from tests.app.db import (
    create_notification,
    create_template,
    create_job,
)


def _create_slow_delivery_notification(template, provider='mmg'):
    now = datetime.utcnow()
    five_minutes_from_now = now + timedelta(minutes=5)

    create_notification(
        template=template,
        status='delivered',
        sent_by=provider,
        updated_at=five_minutes_from_now,
        sent_at=now,
    )


@pytest.fixture(scope='function')
def prepare_current_provider(restore_provider_details):
    initial_provider = get_current_provider('sms')
    dao_update_provider_details(initial_provider)
    initial_provider.updated_at = datetime.utcnow() - timedelta(minutes=30)
    db.session.commit()


def test_should_call_delete_codes_on_delete_verify_codes_task(notify_db_session, mocker):
    mocker.patch('app.celery.scheduled_tasks.delete_codes_older_created_more_than_a_day_ago')
    delete_verify_codes()
    assert scheduled_tasks.delete_codes_older_created_more_than_a_day_ago.call_count == 1


def test_should_call_delete_invotations_on_delete_invitations_task(notify_api, mocker):
    mocker.patch('app.celery.scheduled_tasks.delete_invitations_created_more_than_two_days_ago')
    delete_invitations()
    assert scheduled_tasks.delete_invitations_created_more_than_two_days_ago.call_count == 1


def test_should_update_scheduled_jobs_and_put_on_queue(mocker, sample_template):
    mocked = mocker.patch('app.celery.tasks.process_job.apply_async')

    one_minute_in_the_past = datetime.utcnow() - timedelta(minutes=1)
    job = create_job(sample_template, job_status='scheduled', scheduled_for=one_minute_in_the_past)

    run_scheduled_jobs()

    updated_job = dao_get_job_by_id(job.id)
    assert updated_job.job_status == 'pending'
    mocked.assert_called_with([str(job.id)], queue="job-tasks")


def test_should_update_all_scheduled_jobs_and_put_on_queue(sample_template, mocker):
    mocked = mocker.patch('app.celery.tasks.process_job.apply_async')

    one_minute_in_the_past = datetime.utcnow() - timedelta(minutes=1)
    ten_minutes_in_the_past = datetime.utcnow() - timedelta(minutes=10)
    twenty_minutes_in_the_past = datetime.utcnow() - timedelta(minutes=20)
    job_1 = create_job(sample_template, job_status='scheduled', scheduled_for=one_minute_in_the_past)
    job_2 = create_job(sample_template, job_status='scheduled', scheduled_for=ten_minutes_in_the_past)
    job_3 = create_job(sample_template, job_status='scheduled', scheduled_for=twenty_minutes_in_the_past)

    run_scheduled_jobs()

    assert dao_get_job_by_id(job_1.id).job_status == 'pending'
    assert dao_get_job_by_id(job_2.id).job_status == 'pending'
    assert dao_get_job_by_id(job_2.id).job_status == 'pending'

    mocked.assert_has_calls([
        call([str(job_3.id)], queue="job-tasks"),
        call([str(job_2.id)], queue="job-tasks"),
        call([str(job_1.id)], queue="job-tasks")
    ])


def test_switch_providers_on_slow_delivery_switches_once_then_does_not_switch_if_already_switched(
        notify_api,
        mocker,
        prepare_current_provider,
        sample_user,
        sample_template
):
    mocker.patch('app.provider_details.switch_providers.get_user_by_id', return_value=sample_user)
    starting_provider = get_current_provider('sms')

    _create_slow_delivery_notification(sample_template)
    _create_slow_delivery_notification(sample_template)

    switch_current_sms_provider_on_slow_delivery()

    new_provider = get_current_provider('sms')
    _create_slow_delivery_notification(sample_template, new_provider.identifier)
    _create_slow_delivery_notification(sample_template, new_provider.identifier)
    switch_current_sms_provider_on_slow_delivery()

    final_provider = get_current_provider('sms')

    assert new_provider.identifier != starting_provider.identifier
    assert new_provider.priority < starting_provider.priority
    assert final_provider.identifier == new_provider.identifier


@freeze_time("2017-05-01 14:00:00")
def test_should_send_all_scheduled_notifications_to_deliver_queue(sample_template, mocker):
    mocked = mocker.patch('app.celery.provider_tasks.deliver_sms')
    message_to_deliver = create_notification(template=sample_template, scheduled_for="2017-05-01 13:15")
    create_notification(template=sample_template, scheduled_for="2017-05-01 10:15", status='delivered')
    create_notification(template=sample_template)
    create_notification(template=sample_template, scheduled_for="2017-05-01 14:15")

    scheduled_notifications = dao_get_scheduled_notifications()
    assert len(scheduled_notifications) == 1

    send_scheduled_notifications()

    mocked.apply_async.assert_called_once_with([str(message_to_deliver.id)], queue='send-sms-tasks')
    scheduled_notifications = dao_get_scheduled_notifications()
    assert not scheduled_notifications


def test_check_job_status_task_raises_job_incomplete_error(mocker, sample_template):
    mock_celery = mocker.patch('app.celery.tasks.notify_celery.send_task')
    job = create_job(template=sample_template, notification_count=3,
                     created_at=datetime.utcnow() - timedelta(minutes=31),
                     processing_started=datetime.utcnow() - timedelta(minutes=31),
                     job_status=JOB_STATUS_IN_PROGRESS)
    create_notification(template=sample_template, job=job)
    with pytest.raises(expected_exception=JobIncompleteError) as e:
        check_job_status()
    assert e.value.message == "Job(s) ['{}'] have not completed.".format(str(job.id))

    mock_celery.assert_called_once_with(
        name=TaskNames.PROCESS_INCOMPLETE_JOBS,
        args=([str(job.id)],),
        queue=QueueNames.JOBS
    )


def test_check_job_status_task_raises_job_incomplete_error_when_scheduled_job_is_not_complete(mocker, sample_template):
    mock_celery = mocker.patch('app.celery.tasks.notify_celery.send_task')
    job = create_job(template=sample_template, notification_count=3,
                     created_at=datetime.utcnow() - timedelta(hours=2),
                     scheduled_for=datetime.utcnow() - timedelta(minutes=31),
                     processing_started=datetime.utcnow() - timedelta(minutes=31),
                     job_status=JOB_STATUS_IN_PROGRESS)
    with pytest.raises(expected_exception=JobIncompleteError) as e:
        check_job_status()
    assert e.value.message == "Job(s) ['{}'] have not completed.".format(str(job.id))

    mock_celery.assert_called_once_with(
        name=TaskNames.PROCESS_INCOMPLETE_JOBS,
        args=([str(job.id)],),
        queue=QueueNames.JOBS
    )


def test_check_job_status_task_raises_job_incomplete_error_for_multiple_jobs(mocker, sample_template):
    mock_celery = mocker.patch('app.celery.tasks.notify_celery.send_task')
    job = create_job(template=sample_template, notification_count=3,
                     created_at=datetime.utcnow() - timedelta(hours=2),
                     scheduled_for=datetime.utcnow() - timedelta(minutes=31),
                     processing_started=datetime.utcnow() - timedelta(minutes=31),
                     job_status=JOB_STATUS_IN_PROGRESS)
    job_2 = create_job(template=sample_template, notification_count=3,
                       created_at=datetime.utcnow() - timedelta(hours=2),
                       scheduled_for=datetime.utcnow() - timedelta(minutes=31),
                       processing_started=datetime.utcnow() - timedelta(minutes=31),
                       job_status=JOB_STATUS_IN_PROGRESS)
    with pytest.raises(expected_exception=JobIncompleteError) as e:
        check_job_status()
    assert str(job.id) in e.value.message
    assert str(job_2.id) in e.value.message

    mock_celery.assert_called_once_with(
        name=TaskNames.PROCESS_INCOMPLETE_JOBS,
        args=([str(job.id), str(job_2.id)],),
        queue=QueueNames.JOBS
    )


def test_check_job_status_task_only_sends_old_tasks(mocker, sample_template):
    mock_celery = mocker.patch('app.celery.tasks.notify_celery.send_task')
    job = create_job(
        template=sample_template,
        notification_count=3,
        created_at=datetime.utcnow() - timedelta(hours=2),
        scheduled_for=datetime.utcnow() - timedelta(minutes=31),
        processing_started=datetime.utcnow() - timedelta(minutes=31),
        job_status=JOB_STATUS_IN_PROGRESS
    )
    job_2 = create_job(
        template=sample_template,
        notification_count=3,
        created_at=datetime.utcnow() - timedelta(minutes=31),
        processing_started=datetime.utcnow() - timedelta(minutes=29),
        job_status=JOB_STATUS_IN_PROGRESS
    )
    with pytest.raises(expected_exception=JobIncompleteError) as e:
        check_job_status()
    assert str(job.id) in e.value.message
    assert str(job_2.id) not in e.value.message

    # job 2 not in celery task
    mock_celery.assert_called_once_with(
        name=TaskNames.PROCESS_INCOMPLETE_JOBS,
        args=([str(job.id)],),
        queue=QueueNames.JOBS
    )


def test_check_job_status_task_sets_jobs_to_error(mocker, sample_template):
    mock_celery = mocker.patch('app.celery.tasks.notify_celery.send_task')
    job = create_job(
        template=sample_template,
        notification_count=3,
        created_at=datetime.utcnow() - timedelta(hours=2),
        scheduled_for=datetime.utcnow() - timedelta(minutes=31),
        processing_started=datetime.utcnow() - timedelta(minutes=31),
        job_status=JOB_STATUS_IN_PROGRESS
    )
    job_2 = create_job(
        template=sample_template,
        notification_count=3,
        created_at=datetime.utcnow() - timedelta(minutes=31),
        processing_started=datetime.utcnow() - timedelta(minutes=29),
        job_status=JOB_STATUS_IN_PROGRESS
    )
    with pytest.raises(expected_exception=JobIncompleteError) as e:
        check_job_status()
    assert str(job.id) in e.value.message
    assert str(job_2.id) not in e.value.message

    # job 2 not in celery task
    mock_celery.assert_called_once_with(
        name=TaskNames.PROCESS_INCOMPLETE_JOBS,
        args=([str(job.id)],),
        queue=QueueNames.JOBS
    )
    assert job.job_status == JOB_STATUS_ERROR
    assert job_2.job_status == JOB_STATUS_IN_PROGRESS


def test_replay_created_notifications(notify_db_session, sample_service, mocker):
    email_delivery_queue = mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    sms_delivery_queue = mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')

    sms_template = create_template(service=sample_service, template_type='sms')
    email_template = create_template(service=sample_service, template_type='email')
    older_than = (60 * 60 * 4) + (60 * 15)  # 4 hours 15 minutes
    # notifications expected to be resent
    old_sms = create_notification(template=sms_template, created_at=datetime.utcnow() - timedelta(seconds=older_than),
                                  status='created')
    old_email = create_notification(template=email_template,
                                    created_at=datetime.utcnow() - timedelta(seconds=older_than),
                                    status='created')
    # notifications that are not to be resent
    create_notification(template=sms_template, created_at=datetime.utcnow() - timedelta(seconds=older_than),
                        status='sending')
    create_notification(template=email_template, created_at=datetime.utcnow() - timedelta(seconds=older_than),
                        status='delivered')
    create_notification(template=sms_template, created_at=datetime.utcnow(),
                        status='created')
    create_notification(template=email_template, created_at=datetime.utcnow(),
                        status='created')

    replay_created_notifications()
    email_delivery_queue.assert_called_once_with([str(old_email.id)],
                                                 queue='send-email-tasks')
    sms_delivery_queue.assert_called_once_with([str(old_sms.id)],
                                               queue="send-sms-tasks")


def test_check_job_status_task_does_not_raise_error(sample_template):
    create_job(
        template=sample_template,
        notification_count=3,
        created_at=datetime.utcnow() - timedelta(hours=2),
        scheduled_for=datetime.utcnow() - timedelta(minutes=31),
        processing_started=datetime.utcnow() - timedelta(minutes=31),
        job_status=JOB_STATUS_FINISHED)
    create_job(
        template=sample_template,
        notification_count=3,
        created_at=datetime.utcnow() - timedelta(minutes=31),
        processing_started=datetime.utcnow() - timedelta(minutes=31),
        job_status=JOB_STATUS_FINISHED)

    check_job_status()


@freeze_time("2019-05-30 14:00:00")
def test_check_precompiled_letter_state(mocker, sample_letter_template):
    mock_logger = mocker.patch('app.celery.tasks.current_app.logger.exception')
    mock_create_ticket = mocker.patch('app.celery.nightly_tasks.zendesk_client.create_ticket')

    create_notification(template=sample_letter_template,
                        status=NOTIFICATION_PENDING_VIRUS_CHECK,
                        created_at=datetime.utcnow() - timedelta(seconds=5400))
    create_notification(template=sample_letter_template,
                        status=NOTIFICATION_DELIVERED,
                        created_at=datetime.utcnow() - timedelta(seconds=6000))
    noti_1 = create_notification(template=sample_letter_template,
                                 status=NOTIFICATION_PENDING_VIRUS_CHECK,
                                 created_at=datetime.utcnow() - timedelta(seconds=5401))
    noti_2 = create_notification(template=sample_letter_template,
                                 status=NOTIFICATION_PENDING_VIRUS_CHECK,
                                 created_at=datetime.utcnow() - timedelta(seconds=70000))

    check_precompiled_letter_state()

    message = "2 precompiled letters have been pending-virus-check for over 90 minutes. " \
              "Notifications: ['{}', '{}']".format(noti_2.id, noti_1.id)

    mock_logger.assert_called_once_with(message)
    mock_create_ticket.assert_called_with(
        message=message,
        subject='[test] Letters still pending virus check',
        ticket_type='incident'
    )


@freeze_time("2019-05-30 14:00:00")
def test_check_templated_letter_state_during_bst(mocker, sample_letter_template):
    mock_logger = mocker.patch('app.celery.tasks.current_app.logger.exception')
    mock_create_ticket = mocker.patch('app.celery.nightly_tasks.zendesk_client.create_ticket')

    noti_1 = create_notification(template=sample_letter_template, updated_at=datetime(2019, 5, 1, 12, 0))
    noti_2 = create_notification(template=sample_letter_template, updated_at=datetime(2019, 5, 29, 16, 29))
    create_notification(template=sample_letter_template, updated_at=datetime(2019, 5, 29, 16, 30))
    create_notification(template=sample_letter_template, updated_at=datetime(2019, 5, 29, 17, 29))
    create_notification(template=sample_letter_template, status='delivered', updated_at=datetime(2019, 5, 28, 10, 0))
    create_notification(template=sample_letter_template, updated_at=datetime(2019, 5, 30, 10, 0))

    check_templated_letter_state()

    message = "2 letters were created before 17.30 yesterday and still have 'created' status. " \
              "Notifications: ['{}', '{}']".format(noti_1.id, noti_2.id)

    mock_logger.assert_called_once_with(message)
    mock_create_ticket.assert_called_with(
        message=message,
        subject="[test] Letters still in 'created' status",
        ticket_type='incident'
    )


@freeze_time("2019-01-30 14:00:00")
def test_check_templated_letter_state_during_utc(mocker, sample_letter_template):
    mock_logger = mocker.patch('app.celery.tasks.current_app.logger.exception')
    mock_create_ticket = mocker.patch('app.celery.nightly_tasks.zendesk_client.create_ticket')

    noti_1 = create_notification(template=sample_letter_template, updated_at=datetime(2018, 12, 1, 12, 0))
    noti_2 = create_notification(template=sample_letter_template, updated_at=datetime(2019, 1, 29, 17, 29))
    create_notification(template=sample_letter_template, updated_at=datetime(2019, 1, 29, 17, 30))
    create_notification(template=sample_letter_template, updated_at=datetime(2019, 1, 29, 18, 29))
    create_notification(template=sample_letter_template, status='delivered', updated_at=datetime(2019, 1, 29, 10, 0))
    create_notification(template=sample_letter_template, updated_at=datetime(2019, 1, 30, 10, 0))

    check_templated_letter_state()

    message = "2 letters were created before 17.30 yesterday and still have 'created' status. " \
              "Notifications: ['{}', '{}']".format(noti_1.id, noti_2.id)

    mock_logger.assert_called_once_with(message)
    mock_create_ticket.assert_called_with(
        message=message,
        subject="[test] Letters still in 'created' status",
        ticket_type='incident'
    )


def test_check_for_missing_rows_in_completed_jobs(mocker, sample_email_template):
    mocker.patch('app.celery.tasks.s3.get_job_from_s3', return_value=load_example_csv('multiple_email'))
    mocker.patch('app.encryption.encrypt', return_value="something_encrypted")
    process_row = mocker.patch('app.celery.scheduled_tasks.process_row')

    job = create_job(template=sample_email_template,
                     notification_count=5,
                     job_status=JOB_STATUS_FINISHED,
                     processing_finished=datetime.utcnow() - timedelta(minutes=11))
    for i in range(0, 4):
        create_notification(job=job, job_row_number=i)

    check_for_missing_rows_in_completed_jobs()

    process_row.assert_called_once_with(
        mock.ANY, mock.ANY, job, job.service
    )


def test_check_for_missing_rows_in_completed_jobs_calls_save_email(mocker, sample_email_template):
    mocker.patch('app.celery.tasks.s3.get_job_from_s3', return_value=load_example_csv('multiple_email'))
    save_email_task = mocker.patch('app.celery.tasks.save_email.apply_async')
    mocker.patch('app.encryption.encrypt', return_value="something_encrypted")
    mocker.patch('app.celery.tasks.create_uuid', return_value='uuid')

    job = create_job(template=sample_email_template,
                     notification_count=5,
                     job_status=JOB_STATUS_FINISHED,
                     processing_finished=datetime.utcnow() - timedelta(minutes=11))
    for i in range(0, 4):
        create_notification(job=job, job_row_number=i)

    check_for_missing_rows_in_completed_jobs()
    save_email_task.assert_called_once_with(
        (
            str(job.service_id),
            "uuid",
            "something_encrypted",
        ),
        {},
        queue="database-tasks"
    )
