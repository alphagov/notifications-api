from datetime import datetime, timedelta
from functools import partial
from unittest.mock import call, patch, PropertyMock

from flask import current_app

import pytest
from freezegun import freeze_time

from app.celery import scheduled_tasks
from app.celery.scheduled_tasks import (
    delete_email_notifications_older_than_seven_days,
    delete_inbound_sms_older_than_seven_days,
    delete_invitations,
    delete_notifications_created_more_than_a_week_ago_by_type,
    delete_letter_notifications_older_than_seven_days,
    delete_sms_notifications_older_than_seven_days,
    delete_verify_codes,
    remove_csv_files,
    remove_transformed_dvla_files,
    run_scheduled_jobs,
    s3,
    send_daily_performance_platform_stats,
    send_scheduled_notifications,
    switch_current_sms_provider_on_slow_delivery,
    timeout_job_statistics,
    timeout_notifications
)
from app.clients.performance_platform.performance_platform_client import PerformancePlatformClient
from app.dao.jobs_dao import dao_get_job_by_id
from app.dao.notifications_dao import dao_get_scheduled_notifications
from app.dao.provider_details_dao import (
    dao_update_provider_details,
    get_current_provider
)
from app.models import (
    Service, Template,
    SMS_TYPE, LETTER_TYPE
)
from app.utils import get_london_midnight_in_utc
from tests.app.db import create_notification, create_service, create_template, create_job
from tests.app.conftest import (
    sample_job as create_sample_job,
    sample_notification_history as create_notification_history,
    create_custom_template)
from tests.conftest import set_config_values


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
    assert delete_notifications_created_more_than_a_week_ago_by_type.__wrapped__.__name__ == \
        'delete_notifications_created_more_than_a_week_ago_by_type'
    assert timeout_notifications.__wrapped__.__name__ == 'timeout_notifications'
    assert delete_invitations.__wrapped__.__name__ == 'delete_invitations'
    assert run_scheduled_jobs.__wrapped__.__name__ == 'run_scheduled_jobs'
    assert remove_csv_files.__wrapped__.__name__ == 'remove_csv_files'
    assert send_daily_performance_platform_stats.__wrapped__.__name__ == 'send_daily_performance_platform_stats'
    assert switch_current_sms_provider_on_slow_delivery.__wrapped__.__name__ == \
        'switch_current_sms_provider_on_slow_delivery'
    assert delete_inbound_sms_older_than_seven_days.__wrapped__.__name__ == \
        'delete_inbound_sms_older_than_seven_days'
    assert remove_transformed_dvla_files.__wrapped__.__name__ == \
        'remove_transformed_dvla_files'


def test_should_call_delete_sms_notifications_more_than_week_in_task(notify_api, mocker):
    mocked = mocker.patch('app.celery.scheduled_tasks.delete_notifications_created_more_than_a_week_ago_by_type')
    delete_sms_notifications_older_than_seven_days()
    mocked.assert_called_once_with('sms')


def test_should_call_delete_email_notifications_more_than_week_in_task(notify_api, mocker):
    mocked = mocker.patch('app.celery.scheduled_tasks.delete_notifications_created_more_than_a_week_ago_by_type')
    delete_email_notifications_older_than_seven_days()
    mocked.assert_called_once_with('email')


def test_should_call_delete_letter_notifications_more_than_week_in_task(notify_api, mocker):
    mocked = mocker.patch('app.celery.scheduled_tasks.delete_notifications_created_more_than_a_week_ago_by_type')
    delete_letter_notifications_older_than_seven_days()
    mocked.assert_called_once_with('letter')


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
    mocked.assert_called_with([str(job.id)], queue="job-tasks")


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
        call([str(job_3.id)], queue="job-tasks"),
        call([str(job_2.id)], queue="job-tasks"),
        call([str(job_1.id)], queue="job-tasks")
    ])


@freeze_time('2016-10-18T10:00:00')
def test_will_remove_csv_files_for_jobs_older_than_seven_days(
    notify_db, notify_db_session, mocker, sample_template
):
    mocker.patch('app.celery.scheduled_tasks.s3.remove_job_from_s3')
    """
    Jobs older than seven days are deleted, but only two day's worth (two-day window)
    """
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    just_under_seven_days = seven_days_ago + timedelta(seconds=1)
    eight_days_ago = seven_days_ago - timedelta(days=1)
    nine_days_ago = eight_days_ago - timedelta(days=1)
    just_under_nine_days = nine_days_ago + timedelta(seconds=1)
    nine_days_one_second_ago = nine_days_ago - timedelta(seconds=1)

    create_sample_job(notify_db, notify_db_session, created_at=nine_days_one_second_ago)
    job1_to_delete = create_sample_job(notify_db, notify_db_session, created_at=eight_days_ago)
    job2_to_delete = create_sample_job(notify_db, notify_db_session, created_at=just_under_nine_days)
    create_sample_job(notify_db, notify_db_session, created_at=seven_days_ago)
    create_sample_job(notify_db, notify_db_session, created_at=just_under_seven_days)

    remove_csv_files(job_types=[sample_template.template_type])

    assert s3.remove_job_from_s3.call_args_list == [
        call(job1_to_delete.service_id, job1_to_delete.id),
        call(job2_to_delete.service_id, job2_to_delete.id)
    ]


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
def test_should_send_all_scheduled_notifications_to_deliver_queue(sample_template, mocker):
    mocked = mocker.patch('app.celery.provider_tasks.deliver_sms')
    message_to_deliver = create_notification(template=sample_template, scheduled_for="2017-05-01 13:15")
    create_notification(template=sample_template, scheduled_for="2017-05-01 10:15", status='delivered')
    create_notification(template=sample_template)
    create_notification(template=sample_template, scheduled_for="2017-05-01 14:15")

    scheduled_notifications = dao_get_scheduled_notifications()
    assert len(scheduled_notifications) == 1

    send_scheduled_notifications()

    mocked.apply_async.assert_called_once_with([str(message_to_deliver.id)], queue='send-tasks')
    scheduled_notifications = dao_get_scheduled_notifications()
    assert not scheduled_notifications


def test_timeout_job_statistics_called_with_notification_timeout(notify_api, mocker):
    notify_api.config['SENDING_NOTIFICATIONS_TIMEOUT_PERIOD'] = 999
    dao_mock = mocker.patch('app.celery.scheduled_tasks.dao_timeout_job_statistics')
    timeout_job_statistics()
    dao_mock.assert_called_once_with(999)


def test_should_call_delete_inbound_sms_older_than_seven_days(notify_api, mocker):
    mocker.patch('app.celery.scheduled_tasks.delete_inbound_sms_created_more_than_a_week_ago')
    delete_inbound_sms_older_than_seven_days()
    assert scheduled_tasks.delete_inbound_sms_created_more_than_a_week_ago.call_count == 1


@freeze_time('2017-01-01 10:00:00')
def test_remove_csv_files_filters_by_type(mocker, sample_service):
    mocker.patch('app.celery.scheduled_tasks.s3.remove_job_from_s3')
    """
    Jobs older than seven days are deleted, but only two day's worth (two-day window)
    """
    letter_template = create_template(service=sample_service, template_type=LETTER_TYPE)
    sms_template = create_template(service=sample_service, template_type=SMS_TYPE)

    eight_days_ago = datetime.utcnow() - timedelta(days=8)

    job_to_delete = create_job(template=letter_template, created_at=eight_days_ago)
    create_job(template=sms_template, created_at=eight_days_ago)

    remove_csv_files(job_types=[LETTER_TYPE])

    assert s3.remove_job_from_s3.call_args_list == [
        call(job_to_delete.service_id, job_to_delete.id),
    ]


@freeze_time('2017-01-01 10:00:00')
def test_remove_dvla_transformed_files_removes_expected_files(mocker, sample_service):
    mocker.patch('app.celery.scheduled_tasks.s3.remove_transformed_dvla_file')

    letter_template = create_template(service=sample_service, template_type=LETTER_TYPE)

    job = partial(create_job, template=letter_template)

    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    just_under_seven_days = seven_days_ago + timedelta(seconds=1)
    just_over_seven_days = seven_days_ago - timedelta(seconds=1)
    eight_days_ago = seven_days_ago - timedelta(days=1)
    nine_days_ago = eight_days_ago - timedelta(days=1)
    just_under_nine_days = nine_days_ago + timedelta(seconds=1)
    just_over_nine_days = nine_days_ago - timedelta(seconds=1)

    job(created_at=seven_days_ago)
    job(created_at=just_under_seven_days)
    job_to_delete_1 = job(created_at=just_over_seven_days)
    job_to_delete_2 = job(created_at=eight_days_ago)
    job_to_delete_3 = job(created_at=nine_days_ago)
    job_to_delete_4 = job(created_at=just_under_nine_days)
    job(created_at=just_over_nine_days)

    remove_transformed_dvla_files()

    s3.remove_transformed_dvla_file.assert_has_calls([
        call(job_to_delete_1.id),
        call(job_to_delete_2.id),
        call(job_to_delete_3.id),
        call(job_to_delete_4.id),
    ], any_order=True)
