import pytest

from datetime import datetime, timedelta
from functools import partial

from flask import current_app
from freezegun import freeze_time
from app.celery.scheduled_tasks import s3, send_scheduled_notifications
from app.celery import scheduled_tasks
from app.celery.scheduled_tasks import (
    delete_verify_codes,
    remove_csv_files,
    delete_successful_notifications,
    delete_failed_notifications,
    delete_invitations,
    timeout_notifications,
    run_scheduled_jobs,
    send_daily_performance_platform_stats,
    switch_current_sms_provider_on_slow_delivery
)
from app.clients.performance_platform.performance_platform_client import PerformancePlatformClient
from app.dao.jobs_dao import dao_get_job_by_id
from app.dao.provider_details_dao import (
    dao_update_provider_details,
    get_current_provider
)
from app.models import Service, Template
from app.utils import get_london_midnight_in_utc
from tests.app.db import create_notification, create_service
from tests.app.conftest import (
    sample_job as create_sample_job,
    sample_notification_history as create_notification_history,
    create_custom_template,
    sample_notification)
from tests.conftest import set_config_values
from unittest.mock import call, patch, PropertyMock


def _create_slow_delivery_notification(provider='mmg'):
    now = datetime.utcnow()
    five_minutes_from_now = now + timedelta(minutes=5)
    service = Service.query.get(current_app.config['FUNCTIONAL_TEST_PROVIDER_SERVICE_ID'])
    if not service:
        service = create_service(
            service_id=current_app.config.get('FUNCTIONAL_TEST_PROVIDER_SERVICE_ID')
        )
    template = Template.query.get(current_app.config['FUNCTIONAL_TEST_PROVIDER_SMS_TEMPLATE_ID'])
    if not template:
        template = create_custom_template(
            service=service,
            user=service.users[0],
            template_config_name='FUNCTIONAL_TEST_PROVIDER_SMS_TEMPLATE_ID',
            template_type='sms'
        )

    create_notification(
        template=template,
        status='delivered',
        sent_by=provider,
        updated_at=five_minutes_from_now
    )


@pytest.fixture(scope='function')
def prepare_current_provider(restore_provider_details):
    initial_provider = get_current_provider('sms')
    initial_provider.updated_at = datetime.utcnow() - timedelta(minutes=30)
    dao_update_provider_details(initial_provider)


def test_should_have_decorated_tasks_functions():
    assert delete_verify_codes.__wrapped__.__name__ == 'delete_verify_codes'
    assert delete_successful_notifications.__wrapped__.__name__ == 'delete_successful_notifications'
    assert delete_failed_notifications.__wrapped__.__name__ == 'delete_failed_notifications'
    assert timeout_notifications.__wrapped__.__name__ == 'timeout_notifications'
    assert delete_invitations.__wrapped__.__name__ == 'delete_invitations'
    assert run_scheduled_jobs.__wrapped__.__name__ == 'run_scheduled_jobs'
    assert remove_csv_files.__wrapped__.__name__ == 'remove_csv_files'
    assert send_daily_performance_platform_stats.__wrapped__.__name__ == 'send_daily_performance_platform_stats'
    assert switch_current_sms_provider_on_slow_delivery.__wrapped__.__name__ == \
        'switch_current_sms_provider_on_slow_delivery'


def test_should_call_delete_successful_notifications_more_than_week_in_task(notify_api, mocker):
    mocked = mocker.patch('app.celery.scheduled_tasks.delete_notifications_created_more_than_a_week_ago')
    delete_successful_notifications()
    mocked.assert_called_once_with('delivered')


def test_should_call_delete_failed_notifications_more_than_week_in_task(notify_api, mocker):
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


def test_update_status_of_notifications_after_timeout(notify_api, sample_template):
    with notify_api.test_request_context():
        not1 = create_notification(
            template=sample_template,
            status='sending',
            created_at=datetime.utcnow() - timedelta(
                seconds=current_app.config.get('SENDING_NOTIFICATIONS_TIMEOUT_PERIOD') + 10))
        not2 = create_notification(
            template=sample_template,
            status='created',
            created_at=datetime.utcnow() - timedelta(
                seconds=current_app.config.get('SENDING_NOTIFICATIONS_TIMEOUT_PERIOD') + 10))
        not3 = create_notification(
            template=sample_template,
            status='pending',
            created_at=datetime.utcnow() - timedelta(
                seconds=current_app.config.get('SENDING_NOTIFICATIONS_TIMEOUT_PERIOD') + 10))
        timeout_notifications()
        assert not1.status == 'temporary-failure'
        assert not2.status == 'technical-failure'
        assert not3.status == 'temporary-failure'


def test_not_update_status_of_notification_before_timeout(notify_api, sample_template):
    with notify_api.test_request_context():
        not1 = create_notification(
            template=sample_template,
            status='sending',
            created_at=datetime.utcnow() - timedelta(
                seconds=current_app.config.get('SENDING_NOTIFICATIONS_TIMEOUT_PERIOD') - 10))
        timeout_notifications()
        assert not1.status == 'sending'


def test_should_not_update_status_of_letter_notifications(client, sample_letter_template):
    created_at = datetime.utcnow() - timedelta(days=5)
    not1 = create_notification(template=sample_letter_template, status='sending', created_at=created_at)
    not2 = create_notification(template=sample_letter_template, status='created', created_at=created_at)

    timeout_notifications()

    assert not1.status == 'sending'
    assert not2.status == 'created'


def test_should_update_scheduled_jobs_and_put_on_queue(notify_db, notify_db_session, mocker):
    mocked = mocker.patch('app.celery.tasks.process_job.apply_async')

    one_minute_in_the_past = datetime.utcnow() - timedelta(minutes=1)
    job = create_sample_job(notify_db, notify_db_session, scheduled_for=one_minute_in_the_past, job_status='scheduled')

    run_scheduled_jobs()

    updated_job = dao_get_job_by_id(job.id)
    assert updated_job.job_status == 'pending'
    mocked.assert_called_with([str(job.id)], queue='process-job')


def test_should_update_all_scheduled_jobs_and_put_on_queue(notify_db, notify_db_session, mocker):
    mocked = mocker.patch('app.celery.tasks.process_job.apply_async')

    one_minute_in_the_past = datetime.utcnow() - timedelta(minutes=1)
    ten_minutes_in_the_past = datetime.utcnow() - timedelta(minutes=10)
    twenty_minutes_in_the_past = datetime.utcnow() - timedelta(minutes=20)
    job_1 = create_sample_job(
        notify_db,
        notify_db_session,
        scheduled_for=one_minute_in_the_past,
        job_status='scheduled'
    )
    job_2 = create_sample_job(
        notify_db,
        notify_db_session,
        scheduled_for=ten_minutes_in_the_past,
        job_status='scheduled'
    )
    job_3 = create_sample_job(
        notify_db,
        notify_db_session,
        scheduled_for=twenty_minutes_in_the_past,
        job_status='scheduled'
    )

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

    eligible_job_1 = datetime(2016, 10, 10, 23, 59, 59, 000)
    eligible_job_2 = datetime(2016, 10, 9, 00, 00, 00, 000)
    in_eligible_job_too_new = datetime(2016, 10, 11, 00, 00, 00, 000)
    in_eligible_job_too_old = datetime(2016, 10, 8, 23, 59, 59, 999)

    job_1 = create_sample_job(notify_db, notify_db_session, created_at=eligible_job_1)
    job_2 = create_sample_job(notify_db, notify_db_session, created_at=eligible_job_2)
    create_sample_job(notify_db, notify_db_session, created_at=in_eligible_job_too_new)
    create_sample_job(notify_db, notify_db_session, created_at=in_eligible_job_too_old)

    with freeze_time('2016-10-18T10:00:00'):
        remove_csv_files()
    assert s3.remove_job_from_s3.call_args_list == [call(job_1.service_id, job_1.id), call(job_2.service_id, job_2.id)]


def test_send_daily_performance_stats_calls_does_not_send_if_inactive(
    notify_db,
    notify_db_session,
    sample_template,
    mocker
):
    send_mock = mocker.patch('app.celery.scheduled_tasks.performance_platform_client.send_performance_stats')

    with patch.object(
        PerformancePlatformClient,
        'active',
        new_callable=PropertyMock
    ) as mock_active:
        mock_active.return_value = False
        send_daily_performance_platform_stats()

    assert send_mock.call_count == 0


@freeze_time("2016-01-11 12:30:00")
def test_send_daily_performance_stats_calls_with_correct_totals(
    notify_db,
    notify_db_session,
    sample_template,
    mocker
):
    perf_mock = mocker.patch('app.celery.scheduled_tasks.performance_platform_client.send_performance_stats')

    notification_history = partial(
        create_notification_history,
        notify_db,
        notify_db_session,
        sample_template,
        status='delivered'
    )

    notification_history(notification_type='email')
    notification_history(notification_type='sms')

    # Create some notifications for the day before
    yesterday = datetime(2016, 1, 10, 15, 30, 0, 0)
    with freeze_time(yesterday):
        notification_history(notification_type='sms')
        notification_history(notification_type='sms')
        notification_history(notification_type='email')
        notification_history(notification_type='email')
        notification_history(notification_type='email')

    with patch.object(
        PerformancePlatformClient,
        'active',
        new_callable=PropertyMock
    ) as mock_active:
        mock_active.return_value = True
        send_daily_performance_platform_stats()

        perf_mock.assert_has_calls([
            call(get_london_midnight_in_utc(yesterday), 'sms', 2, 'day'),
            call(get_london_midnight_in_utc(yesterday), 'email', 3, 'day')
        ])


def test_switch_current_sms_provider_on_slow_delivery_does_not_run_if_config_unset(
    notify_api,
    mocker
):
    get_notifications_mock = mocker.patch(
        'app.celery.scheduled_tasks.is_delivery_slow_for_provider'
    )
    toggle_sms_mock = mocker.patch('app.celery.scheduled_tasks.dao_toggle_sms_provider')

    with set_config_values(notify_api, {
        'FUNCTIONAL_TEST_PROVIDER_SERVICE_ID': None,
        'FUNCTIONAL_TEST_PROVIDER_SMS_TEMPLATE_ID': None
    }):
        switch_current_sms_provider_on_slow_delivery()

    assert get_notifications_mock.called is False
    assert toggle_sms_mock.called is False


def test_switch_providers_on_slow_delivery_runs_if_config_set(
    notify_api,
    mocker,
    prepare_current_provider
):
    get_notifications_mock = mocker.patch(
        'app.celery.scheduled_tasks.is_delivery_slow_for_provider',
        return_value=[]
    )

    with set_config_values(notify_api, {
        'FUNCTIONAL_TEST_PROVIDER_SERVICE_ID': '7954469d-8c6d-43dc-b8f7-86be2d69f5f3',
        'FUNCTIONAL_TEST_PROVIDER_SMS_TEMPLATE_ID': '331a63e6-f1aa-4588-ad3f-96c268788ae7'
    }):
        switch_current_sms_provider_on_slow_delivery()

    assert get_notifications_mock.called is True


def test_switch_providers_triggers_on_slow_notification_delivery(
    notify_api,
    mocker,
    prepare_current_provider,
    sample_user
):
    mocker.patch('app.provider_details.switch_providers.get_user_by_id', return_value=sample_user)
    starting_provider = get_current_provider('sms')

    with set_config_values(notify_api, {
        'FUNCTIONAL_TEST_PROVIDER_SERVICE_ID': '7954469d-8c6d-43dc-b8f7-86be2d69f5f3',
        'FUNCTIONAL_TEST_PROVIDER_SMS_TEMPLATE_ID': '331a63e6-f1aa-4588-ad3f-96c268788ae7'
    }):
        _create_slow_delivery_notification(starting_provider.identifier)
        _create_slow_delivery_notification(starting_provider.identifier)
        switch_current_sms_provider_on_slow_delivery()

    new_provider = get_current_provider('sms')
    assert new_provider.identifier != starting_provider.identifier
    assert new_provider.priority < starting_provider.priority


def test_switch_providers_on_slow_delivery_does_not_switch_if_already_switched(
    notify_api,
    mocker,
    prepare_current_provider,
    sample_user
):
    mocker.patch('app.provider_details.switch_providers.get_user_by_id', return_value=sample_user)
    starting_provider = get_current_provider('sms')

    with set_config_values(notify_api, {
        'FUNCTIONAL_TEST_PROVIDER_SERVICE_ID': '7954469d-8c6d-43dc-b8f7-86be2d69f5f3',
        'FUNCTIONAL_TEST_PROVIDER_SMS_TEMPLATE_ID': '331a63e6-f1aa-4588-ad3f-96c268788ae7'
    }):
        _create_slow_delivery_notification()
        _create_slow_delivery_notification()

        switch_current_sms_provider_on_slow_delivery()
        switch_current_sms_provider_on_slow_delivery()

    new_provider = get_current_provider('sms')
    assert new_provider.identifier != starting_provider.identifier
    assert new_provider.priority < starting_provider.priority


def test_switch_providers_on_slow_delivery_does_not_switch_based_on_older_notifications(
    notify_api,
    mocker,
    prepare_current_provider,
    sample_user,

):
    """
    Assume we have three slow delivery notifications for the current provider x. This triggers
    a switch to provider y. If we experience some slow delivery notifications on this provider,
    we switch back to provider x.

    Provider x had three slow deliveries initially, but we do not want to trigger another switch
    based on these as they are old. We only want to look for slow notifications after the point at
    which we switched back to provider x.
    """
    mocker.patch('app.provider_details.switch_providers.get_user_by_id', return_value=sample_user)
    starting_provider = get_current_provider('sms')

    with set_config_values(notify_api, {
        'FUNCTIONAL_TEST_PROVIDER_SERVICE_ID': '7954469d-8c6d-43dc-b8f7-86be2d69f5f3',
        'FUNCTIONAL_TEST_PROVIDER_SMS_TEMPLATE_ID': '331a63e6-f1aa-4588-ad3f-96c268788ae7'
    }):
        # Provider x -> y
        _create_slow_delivery_notification(starting_provider.identifier)
        _create_slow_delivery_notification(starting_provider.identifier)
        _create_slow_delivery_notification(starting_provider.identifier)
        switch_current_sms_provider_on_slow_delivery()

        current_provider = get_current_provider('sms')
        assert current_provider.identifier != starting_provider.identifier

        # Provider y -> x
        _create_slow_delivery_notification(current_provider.identifier)
        _create_slow_delivery_notification(current_provider.identifier)
        switch_current_sms_provider_on_slow_delivery()

        new_provider = get_current_provider('sms')
        assert new_provider.identifier != current_provider.identifier

        # Expect to stay on provider x
        switch_current_sms_provider_on_slow_delivery()
        current_provider = get_current_provider('sms')
        assert starting_provider.identifier == current_provider.identifier


@freeze_time("2017-05-01 14:00:00")
def test_should_send_all_scheduled_notifications_to_deliver_queue(notify_db,
                                                                  notify_db_session,
                                                                  sample_template, mocker):
    mocked = mocker.patch('app.celery.provider_tasks.deliver_sms')
    message_to_deliver = sample_notification(notify_db=notify_db, notify_db_session=notify_db_session,
                                             template=sample_template, scheduled_for="2017-05-01 13:50:00")
    sample_notification(notify_db=notify_db, notify_db_session=notify_db_session,
                        template=sample_template, scheduled_for="2017-05-01 10:50:00", status='delivered')
    sample_notification(notify_db=notify_db, notify_db_session=notify_db_session,
                        template=sample_template)
    sample_notification(notify_db=notify_db, notify_db_session=notify_db_session,
                        template=sample_template, scheduled_for="2017-05-01 14:30:00")

    send_scheduled_notifications()

    mocked.apply_async.assert_called_once_with([str(message_to_deliver.id)], queue='send-sms')
