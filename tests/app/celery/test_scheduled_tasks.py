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
                                        run_scheduled_jobs,
                                        switch_providers_on_slow_delivery)
from app.dao.jobs_dao import dao_get_job_by_id
from app.dao.provider_details_dao import (
    dao_update_provider_details,
    get_provider_details_by_identifier,
    get_alternative_sms_provider,
    get_current_provider
)
from tests.app.conftest import (
    sample_notification as create_sample_notification,
    sample_service as create_sample_service,
    sample_template as create_sample_template,
    sample_job,
    set_primary_sms_provider
)
from unittest.mock import call


def set_equal_priorities_for_sms_providers():
    primary_provider = get_provider_details_by_identifier('mmg')
    secondary_provider = get_alternative_sms_provider('firetext')

    primary_provider.priority = 10
    secondary_provider.priority = 10

    dao_update_provider_details(primary_provider)
    dao_update_provider_details(secondary_provider)


def create_sample_functional_test_slow_delivery_notification(
    notify_db,
    notify_db_session,
    created_at=None,
    sent_at=None,
    sent_by=None
):
    service = create_sample_service(
        notify_db,
        notify_db_session,
        service_id=current_app.config.get('FUNCTIONAL_TEST_SERVICE_ID')
    )

    template = create_sample_template(
        notify_db,
        notify_db_session,
        template_id=current_app.config.get('FUNCTIONAL_TEST_TEMPLATE_ID'),
        service=service
    )
    notification = create_sample_notification(
        notify_db,
        notify_db_session,
        service=service,
        template=template,
        created_at=created_at,
        sent_at=sent_at,
        sent_by=sent_by,
        status='sending'
    )

    return notification


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
        not1 = create_sample_notification(
            notify_db,
            notify_db_session,
            service=sample_service,
            template=sample_template,
            status='sending',
            created_at=datetime.utcnow() - timedelta(
                seconds=current_app.config.get('SENDING_NOTIFICATIONS_TIMEOUT_PERIOD') + 10))
        not2 = create_sample_notification(
            notify_db,
            notify_db_session,
            service=sample_service,
            template=sample_template,
            status='created',
            created_at=datetime.utcnow() - timedelta(
                seconds=current_app.config.get('SENDING_NOTIFICATIONS_TIMEOUT_PERIOD') + 10))
        not3 = create_sample_notification(
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
        not1 = create_sample_notification(
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


def test_switch_sms_providers_old_slow_delivery_notifications_does_not_switch(
    notify_db,
    notify_db_session,
    restore_provider_details,
    mocker
):
    set_primary_sms_provider('mmg')

    # Create a notification '10 mins, 1 second ago'
    create_sample_functional_test_slow_delivery_notification(
        notify_db,
        notify_db_session,
        created_at=datetime.utcnow() - timedelta(minutes=10, seconds=1),
        sent_at=datetime.utcnow(),
        sent_by='mmg'
    )

    # Should not switch providers
    switch_providers_on_slow_delivery()

    current_provider = get_current_provider('sms')

    assert current_provider.identifier == 'mmg'


def test_switch_sms_providers_mmg_slow_delivery_sets_firetext_as_primary(
    notify_db,
    notify_db_session,
    restore_provider_details,
    mocker
):
    set_primary_sms_provider('mmg')

    create_sample_functional_test_slow_delivery_notification(
        notify_db,
        notify_db_session,
        created_at=datetime.utcnow() - timedelta(minutes=5),
        sent_at=datetime.utcnow(),
        sent_by='mmg'
    )

    # Should attempt switch to firetext
    switch_providers_on_slow_delivery()

    current_provider = get_current_provider('sms')

    assert current_provider.identifier == 'firetext'


def test_switch_sms_providers_firetext_slow_delivery_sets_mmg_as_primary(
    notify_db,
    notify_db_session,
    restore_provider_details,
    mocker
):
    set_primary_sms_provider('firetext')

    # Should attempt switch to mmg
    create_sample_functional_test_slow_delivery_notification(
        notify_db,
        notify_db_session,
        created_at=datetime.utcnow() - timedelta(minutes=5),
        sent_at=datetime.utcnow(),
        sent_by='firetext'
    )

    switch_providers_on_slow_delivery()

    current_provider = get_current_provider('sms')

    assert current_provider.identifier == 'mmg'


def test_switch_sms_providers_with_equal_priorities_sets_firetext_as_primary(
    notify_db,
    notify_db_session,
    restore_provider_details,
    mocker
):
    set_equal_priorities_for_sms_providers()

    create_sample_functional_test_slow_delivery_notification(
        notify_db,
        notify_db_session,
        created_at=datetime.utcnow() - timedelta(minutes=5),
        sent_at=datetime.utcnow(),
        sent_by='mmg'
    )

    # Should attempt switch to firetext
    switch_providers_on_slow_delivery()

    primary_provider = get_provider_details_by_identifier('firetext')
    secondary_provider = get_provider_details_by_identifier('mmg')

    assert primary_provider.priority < secondary_provider.priority


def test_switch_sms_providers_mmg_already_primary_does_not_update(
    notify_db,
    notify_db_session,
    restore_provider_details,
    mocker
):
    set_primary_sms_provider('mmg')

    provider_mmg_before = get_provider_details_by_identifier('mmg')
    provider_firetext_before = get_provider_details_by_identifier('firetext')

    create_sample_functional_test_slow_delivery_notification(
        notify_db,
        notify_db_session,
        created_at=datetime.utcnow() - timedelta(minutes=5),
        sent_at=datetime.utcnow(),
        sent_by='firetext'
    )

    # Should attempt switch to mmg
    switch_providers_on_slow_delivery()

    provider_mmg_after = get_provider_details_by_identifier('mmg')
    provider_firetext_after = get_provider_details_by_identifier('firetext')

    assert provider_mmg_before.priority == provider_mmg_after.priority
    assert provider_firetext_before.priority == provider_firetext_after.priority

    assert provider_mmg_before.version == provider_mmg_after.version
    assert provider_firetext_before.version == provider_firetext_after.version
