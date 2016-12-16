from datetime import datetime, timedelta

from flask import current_app
from freezegun import freeze_time
from app.celery.scheduled_tasks import s3
from app.celery import scheduled_tasks
from app.celery.scheduled_tasks import (delete_verify_codes,
                                        remove_csv_files,
                                        delete_successful_notifications,
                                        delete_failed_notifications,
                                        delete_invitations,
                                        timeout_notifications,
                                        run_scheduled_jobs)
from app.dao.jobs_dao import dao_get_job_by_id
from tests.app.conftest import sample_notification, sample_job
from unittest.mock import call


def test_should_have_decorated_tasks_functions():
    assert delete_verify_codes.__wrapped__.__name__ == 'delete_verify_codes'
    assert delete_successful_notifications.__wrapped__.__name__ == 'delete_successful_notifications'
    assert delete_failed_notifications.__wrapped__.__name__ == 'delete_failed_notifications'
    assert timeout_notifications.__wrapped__.__name__ == 'timeout_notifications'
    assert delete_invitations.__wrapped__.__name__ == 'delete_invitations'
    assert run_scheduled_jobs.__wrapped__.__name__ == 'run_scheduled_jobs'
    assert remove_csv_files.__wrapped__.__name__ == 'remove_csv_files'


def test_should_call_delete_notifications_more_than_week_in_task(notify_api, mocker):
    mocked = mocker.patch('app.celery.scheduled_tasks.delete_notifications_created_more_than_a_week_ago')
    delete_successful_notifications()
    assert mocked.assert_called_with('delivered')
    assert scheduled_tasks.delete_notifications_created_more_than_a_week_ago.call_count == 1


def test_should_call_delete_notifications_more_than_week_in_task(notify_api, mocker):
    mocker.patch('app.celery.scheduled_tasks.delete_notifications_created_more_than_a_week_ago')
    delete_failed_notifications()
    assert scheduled_tasks.delete_notifications_created_more_than_a_week_ago.call_count == 4


def test_should_call_delete_codes_on_delete_verify_codes_task(notify_api, mocker):
    mocker.patch('app.celery.scheduled_tasks.delete_codes_older_created_more_than_a_day_ago')
    delete_verify_codes()
    assert scheduled_tasks.delete_codes_older_created_more_than_a_day_ago.call_count == 1


def test_should_call_delete_invotations_on_delete_invitations_task(notify_api, mocker):
    mocker.patch('app.celery.scheduled_tasks.delete_invitations_created_more_than_two_days_ago')
    delete_invitations()
    assert scheduled_tasks.delete_invitations_created_more_than_two_days_ago.call_count == 1


def test_update_status_of_notifications_after_timeout(notify_api,
                                                      notify_db,
                                                      notify_db_session,
                                                      sample_service,
                                                      sample_template,
                                                      mmg_provider):
    with notify_api.test_request_context():
        not1 = sample_notification(
            notify_db,
            notify_db_session,
            service=sample_service,
            template=sample_template,
            status='sending',
            created_at=datetime.utcnow() - timedelta(
                seconds=current_app.config.get('SENDING_NOTIFICATIONS_TIMEOUT_PERIOD') + 10))
        not2 = sample_notification(
            notify_db,
            notify_db_session,
            service=sample_service,
            template=sample_template,
            status='created',
            created_at=datetime.utcnow() - timedelta(
                seconds=current_app.config.get('SENDING_NOTIFICATIONS_TIMEOUT_PERIOD') + 10))
        not3 = sample_notification(
            notify_db,
            notify_db_session,
            service=sample_service,
            template=sample_template,
            status='pending',
            created_at=datetime.utcnow() - timedelta(
                seconds=current_app.config.get('SENDING_NOTIFICATIONS_TIMEOUT_PERIOD') + 10))
        timeout_notifications()
        assert not1.status == 'temporary-failure'
        assert not2.status == 'technical-failure'
        assert not3.status == 'temporary-failure'


def test_not_update_status_of_notification_before_timeout(notify_api,
                                                          notify_db,
                                                          notify_db_session,
                                                          sample_service,
                                                          sample_template,
                                                          mmg_provider):
    with notify_api.test_request_context():
        not1 = sample_notification(
            notify_db,
            notify_db_session,
            service=sample_service,
            template=sample_template,
            status='sending',
            created_at=datetime.utcnow() - timedelta(
                seconds=current_app.config.get('SENDING_NOTIFICATIONS_TIMEOUT_PERIOD') - 10))
        timeout_notifications()
        assert not1.status == 'sending'


def test_should_update_scheduled_jobs_and_put_on_queue(notify_db, notify_db_session, mocker):
    mocked = mocker.patch('app.celery.tasks.process_job.apply_async')

    one_minute_in_the_past = datetime.utcnow() - timedelta(minutes=1)
    job = sample_job(notify_db, notify_db_session, scheduled_for=one_minute_in_the_past, job_status='scheduled')

    run_scheduled_jobs()

    updated_job = dao_get_job_by_id(job.id)
    assert updated_job.job_status == 'pending'
    mocked.assert_called_with([str(job.id)], queue='process-job')


def test_should_update_all_scheduled_jobs_and_put_on_queue(notify_db, notify_db_session, mocker):
    mocked = mocker.patch('app.celery.tasks.process_job.apply_async')

    one_minute_in_the_past = datetime.utcnow() - timedelta(minutes=1)
    ten_minutes_in_the_past = datetime.utcnow() - timedelta(minutes=10)
    twenty_minutes_in_the_past = datetime.utcnow() - timedelta(minutes=20)
    job_1 = sample_job(notify_db, notify_db_session, scheduled_for=one_minute_in_the_past, job_status='scheduled')
    job_2 = sample_job(notify_db, notify_db_session, scheduled_for=ten_minutes_in_the_past, job_status='scheduled')
    job_3 = sample_job(notify_db, notify_db_session, scheduled_for=twenty_minutes_in_the_past, job_status='scheduled')

    run_scheduled_jobs()

    assert dao_get_job_by_id(job_1.id).job_status == 'pending'
    assert dao_get_job_by_id(job_2.id).job_status == 'pending'
    assert dao_get_job_by_id(job_2.id).job_status == 'pending'

    mocked.assert_has_calls([
        call([str(job_3.id)], queue='process-job'),
        call([str(job_2.id)], queue='process-job'),
        call([str(job_1.id)], queue='process-job')
    ])


def test_will_remove_csv_files_for_jobs_older_than_seven_days(notify_db, notify_db_session, mocker):
    mocker.patch('app.celery.scheduled_tasks.s3.remove_job_from_s3')

    one_millisecond_before_midnight = datetime(2016, 10, 9, 23, 59, 59, 999)
    midnight = datetime(2016, 10, 10, 0, 0, 0, 0)
    one_millisecond_past_midnight = datetime(2016, 10, 10, 0, 0, 0, 1)

    job_1 = sample_job(notify_db, notify_db_session, created_at=one_millisecond_before_midnight)
    sample_job(notify_db, notify_db_session, created_at=midnight)
    sample_job(notify_db, notify_db_session, created_at=one_millisecond_past_midnight)

    with freeze_time('2016-10-17T00:00:00'):
        remove_csv_files()
    s3.remove_job_from_s3.assert_called_once_with(job_1.service_id, job_1.id)
