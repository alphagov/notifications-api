from datetime import datetime, timedelta
from functools import partial
from unittest.mock import call, patch, PropertyMock
import pytz
import functools
from flask import current_app

import pytest
from freezegun import freeze_time

from app import db
from app.celery import scheduled_tasks
from app.celery.scheduled_tasks import (
    check_job_status,
    delete_dvla_response_files_older_than_seven_days,
    delete_email_notifications_older_than_seven_days,
    delete_inbound_sms_older_than_seven_days,
    delete_invitations,
    delete_notifications_created_more_than_a_week_ago_by_type,
    delete_letter_notifications_older_than_seven_days,
    delete_sms_notifications_older_than_seven_days,
    delete_verify_codes,
    raise_alert_if_letter_notifications_still_sending,
    remove_csv_files,
    remove_transformed_dvla_files,
    run_scheduled_jobs,
    run_letter_jobs,
    trigger_letter_pdfs_for_day,
    run_letter_api_notifications,
    populate_monthly_billing,
    s3,
    send_daily_performance_platform_stats,
    send_scheduled_notifications,
    send_total_sent_notifications_to_performance_platform,
    switch_current_sms_provider_on_slow_delivery,
    timeout_job_statistics,
    timeout_notifications,
    daily_stats_template_usage_by_month,
    letter_raise_alert_if_no_ack_file_for_zip
)
from app.clients.performance_platform.performance_platform_client import PerformancePlatformClient
from app.config import QueueNames, TaskNames
from app.dao.jobs_dao import dao_get_job_by_id
from app.dao.notifications_dao import dao_get_scheduled_notifications
from app.dao.provider_details_dao import (
    dao_update_provider_details,
    get_current_provider
)
from app.models import (
    MonthlyBilling,
    NotificationHistory,
    Service,
    StatsTemplateUsageByMonth,
    JOB_STATUS_READY_TO_SEND,
    JOB_STATUS_IN_PROGRESS,
    JOB_STATUS_SENT_TO_DVLA,
    KEY_TYPE_TEST,
    LETTER_TYPE,
    NOTIFICATION_CREATED,
    NOTIFICATION_PENDING,
    SMS_TYPE
)
from app.utils import get_london_midnight_in_utc
from app.v2.errors import JobIncompleteError
from tests.app.db import create_notification, create_service, create_template, create_job, create_rate

from tests.app.conftest import (
    sample_job as create_sample_job,
    sample_notification_history as create_notification_history,
    sample_template as create_sample_template,
    create_custom_template,
    datetime_in_past
)
from tests.app.aws.test_s3 import single_s3_object_stub
from tests.conftest import set_config_values


def _create_slow_delivery_notification(provider='mmg'):
    now = datetime.utcnow()
    five_minutes_from_now = now + timedelta(minutes=5)
    service = Service.query.get(current_app.config['FUNCTIONAL_TEST_PROVIDER_SERVICE_ID'])
    if not service:
        service = create_service(
            service_id=current_app.config.get('FUNCTIONAL_TEST_PROVIDER_SERVICE_ID')
        )

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


@pytest.mark.skip(reason="This doesn't actually test the celery task wraps the function")
def test_should_have_decorated_tasks_functions():
    """
    TODO: This test needs to be reviewed as this doesn't actually
    test that the celery task is wrapping the function. We're also
    running similar tests elsewhere which also need review.
    """
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
    assert delete_dvla_response_files_older_than_seven_days.__wrapped__.__name__ == \
        'delete_dvla_response_files_older_than_seven_days'
    assert populate_monthly_billing.__wrapped__.__name__ == \
        'populate_monthly_billing'


@pytest.fixture(scope='function')
def prepare_current_provider(restore_provider_details):
    initial_provider = get_current_provider('sms')
    initial_provider.updated_at = datetime.utcnow() - timedelta(minutes=30)
    dao_update_provider_details(initial_provider)


def test_should_call_delete_sms_notifications_more_than_week_in_task(notify_api, mocker):
    mocked = mocker.patch('app.celery.scheduled_tasks.delete_notifications_created_more_than_a_week_ago_by_type')
    delete_sms_notifications_older_than_seven_days()
    mocked.assert_called_once_with('sms')


def test_should_call_delete_email_notifications_more_than_week_in_task(notify_api, mocker):
    mocked_notifications = mocker.patch(
        'app.celery.scheduled_tasks.delete_notifications_created_more_than_a_week_ago_by_type')
    delete_email_notifications_older_than_seven_days()
    mocked_notifications.assert_called_once_with('email')


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


def test_send_daily_performance_stats_calls_does_not_send_if_inactive(client, mocker):
    send_mock = mocker.patch('app.celery.scheduled_tasks.total_sent_notifications.send_total_notifications_sent_for_day_stats')  # noqa

    with patch.object(
        PerformancePlatformClient,
        'active',
        new_callable=PropertyMock
    ) as mock_active:
        mock_active.return_value = False
        send_daily_performance_platform_stats()

    assert send_mock.call_count == 0


@freeze_time("2016-01-11 12:30:00")
def test_send_total_sent_notifications_to_performance_platform_calls_with_correct_totals(
    notify_db,
    notify_db_session,
    sample_template,
    mocker
):
    perf_mock = mocker.patch('app.celery.scheduled_tasks.total_sent_notifications.send_total_notifications_sent_for_day_stats')  # noqa

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
        send_total_sent_notifications_to_performance_platform()

        perf_mock.assert_has_calls([
            call(get_london_midnight_in_utc(yesterday), 'sms', 2),
            call(get_london_midnight_in_utc(yesterday), 'email', 3)
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

    mocked.apply_async.assert_called_once_with([str(message_to_deliver.id)], queue='send-sms-tasks')
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


def test_remove_dvla_transformed_files_does_not_remove_files(mocker, sample_service):
    mocker.patch('app.celery.scheduled_tasks.s3.remove_transformed_dvla_file')

    letter_template = create_template(service=sample_service, template_type=LETTER_TYPE)

    job = partial(create_job, template=letter_template)

    yesterday = datetime.utcnow() - timedelta(days=1)
    six_days_ago = datetime.utcnow() - timedelta(days=6)
    seven_days_ago = six_days_ago - timedelta(days=1)
    just_over_nine_days = seven_days_ago - timedelta(days=2, seconds=1)

    job(created_at=yesterday)
    job(created_at=six_days_ago)
    job(created_at=seven_days_ago)
    job(created_at=just_over_nine_days)

    remove_transformed_dvla_files()

    s3.remove_transformed_dvla_file.assert_has_calls([])


@freeze_time("2016-01-01 11:00:00")
def test_delete_dvla_response_files_older_than_seven_days_removes_old_files(notify_api, mocker):
    AFTER_SEVEN_DAYS = datetime_in_past(days=8)
    single_page_s3_objects = [{
        "Contents": [
            single_s3_object_stub('bar/foo1.txt', AFTER_SEVEN_DAYS),
            single_s3_object_stub('bar/foo2.txt', AFTER_SEVEN_DAYS),
        ]
    }]
    mocker.patch(
        'app.celery.scheduled_tasks.s3.get_s3_bucket_objects', return_value=single_page_s3_objects[0]["Contents"]
    )
    remove_s3_mock = mocker.patch('app.celery.scheduled_tasks.s3.remove_s3_object')

    delete_dvla_response_files_older_than_seven_days()

    remove_s3_mock.assert_has_calls([
        call(current_app.config['DVLA_RESPONSE_BUCKET_NAME'], single_page_s3_objects[0]["Contents"][0]["Key"]),
        call(current_app.config['DVLA_RESPONSE_BUCKET_NAME'], single_page_s3_objects[0]["Contents"][1]["Key"])
    ])


@freeze_time("2016-01-01 11:00:00")
def test_delete_dvla_response_files_older_than_seven_days_does_not_remove_files(notify_api, mocker):
    START_DATE = datetime_in_past(days=9)
    JUST_BEFORE_START_DATE = datetime_in_past(days=9, seconds=1)
    END_DATE = datetime_in_past(days=7)
    JUST_AFTER_END_DATE = END_DATE + timedelta(seconds=1)

    single_page_s3_objects = [{
        "Contents": [
            single_s3_object_stub('bar/foo1.txt', JUST_BEFORE_START_DATE),
            single_s3_object_stub('bar/foo2.txt', START_DATE),
            single_s3_object_stub('bar/foo3.txt', END_DATE),
            single_s3_object_stub('bar/foo4.txt', JUST_AFTER_END_DATE),
        ]
    }]
    mocker.patch(
        'app.celery.scheduled_tasks.s3.get_s3_bucket_objects', return_value=single_page_s3_objects[0]["Contents"]
    )
    remove_s3_mock = mocker.patch('app.celery.scheduled_tasks.s3.remove_s3_object')
    delete_dvla_response_files_older_than_seven_days()

    remove_s3_mock.assert_not_called()


@freeze_time("2018-01-17 17:00:00")
def test_alert_if_letter_notifications_still_sending(sample_letter_template, mocker):
    yesterday = datetime(2018, 1, 16, 13, 30)
    create_notification(template=sample_letter_template, status='sending', sent_at=yesterday)

    mock_celery = mocker.patch("app.celery.scheduled_tasks.deskpro_client.create_ticket")

    raise_alert_if_letter_notifications_still_sending()

    mock_celery.assert_called_once_with(
        subject="[test] Letters still sending",
        message="There are 1 letters in the 'sending' state from Tuesday 16 January",
        ticket_type='alert'
    )


@freeze_time("2018-01-17 17:00:00")
def test_alert_if_letter_notifications_still_sending_only_alerts_sending(sample_letter_template, mocker):
    yesterday = datetime(2018, 1, 16, 13, 30)
    create_notification(template=sample_letter_template, status='sending', sent_at=yesterday)
    create_notification(template=sample_letter_template, status='delivered', sent_at=yesterday)
    create_notification(template=sample_letter_template, status='failed', sent_at=yesterday)

    mock_celery = mocker.patch("app.celery.scheduled_tasks.deskpro_client.create_ticket")

    raise_alert_if_letter_notifications_still_sending()

    mock_celery.assert_called_once_with(
        subject="[test] Letters still sending",
        message="There are 1 letters in the 'sending' state from Tuesday 16 January",
        ticket_type='alert'
    )


@freeze_time("2018-01-17 17:00:00")
def test_alert_if_letter_notifications_still_sending_only_alerts_previous_day(sample_letter_template, mocker):
    day_before_yesterday = datetime(2018, 1, 15, 13, 30)
    create_notification(template=sample_letter_template, status='sending', sent_at=day_before_yesterday)

    mock_celery = mocker.patch("app.celery.scheduled_tasks.deskpro_client.create_ticket")

    raise_alert_if_letter_notifications_still_sending()

    assert not mock_celery.called


@freeze_time("2018-01-14 17:00:00")
def test_alert_if_letter_notifications_still_sending_does_nothing_on_the_weekend(sample_letter_template, mocker):
    yesterday = datetime(2018, 1, 13, 13, 30)
    create_notification(template=sample_letter_template, status='sending', sent_at=yesterday)

    mock_celery = mocker.patch("app.celery.scheduled_tasks.deskpro_client.create_ticket")

    raise_alert_if_letter_notifications_still_sending()

    assert not mock_celery.called


@freeze_time("2018-01-15 17:00:00")
def test_monday_alert_if_letter_notifications_still_sending_reports_friday_letters(sample_letter_template, mocker):
    friday = datetime(2018, 1, 12, 13, 30)
    yesterday = datetime(2018, 1, 14, 13, 30)

    create_notification(template=sample_letter_template, status='sending', sent_at=friday)
    create_notification(template=sample_letter_template, status='sending', sent_at=yesterday)

    mock_celery = mocker.patch("app.celery.scheduled_tasks.deskpro_client.create_ticket")

    raise_alert_if_letter_notifications_still_sending()

    mock_celery.assert_called_once_with(
        subject="[test] Letters still sending",
        message="There are 2 letters in the 'sending' state from Friday 12 January",
        ticket_type='alert'
    )


@freeze_time("2017-07-12 02:00:00")
def test_populate_monthly_billing_populates_correctly(sample_template):
    yesterday = datetime(2017, 7, 11, 13, 30)
    jul_month_start = datetime(2017, 6, 30, 23)
    jul_month_end = datetime(2017, 7, 31, 22, 59, 59, 99999)
    create_rate(datetime(2016, 1, 1), 0.0123, 'sms')

    create_notification(template=sample_template, status='delivered', created_at=yesterday)
    create_notification(template=sample_template, status='delivered', created_at=yesterday - timedelta(days=1))
    create_notification(template=sample_template, status='delivered', created_at=yesterday + timedelta(days=1))
    # not included in billing
    create_notification(template=sample_template, status='delivered', created_at=yesterday - timedelta(days=30))

    populate_monthly_billing()

    monthly_billing = MonthlyBilling.query.order_by(MonthlyBilling.notification_type).all()

    assert len(monthly_billing) == 3

    assert monthly_billing[0].service_id == sample_template.service_id
    assert monthly_billing[0].start_date == jul_month_start
    assert monthly_billing[0].end_date == jul_month_end
    assert monthly_billing[0].notification_type == 'email'
    assert monthly_billing[0].monthly_totals == []

    assert monthly_billing[1].service_id == sample_template.service_id
    assert monthly_billing[1].start_date == jul_month_start
    assert monthly_billing[1].end_date == jul_month_end
    assert monthly_billing[1].notification_type == 'sms'
    assert sorted(monthly_billing[1].monthly_totals[0]) == sorted(
        {
            'international': False,
            'rate_multiplier': 1,
            'billing_units': 3,
            'rate': 0.0123,
            'total_cost': 0.0369
        }
    )

    assert monthly_billing[2].service_id == sample_template.service_id
    assert monthly_billing[2].start_date == jul_month_start
    assert monthly_billing[2].end_date == jul_month_end
    assert monthly_billing[2].notification_type == 'letter'
    assert monthly_billing[2].monthly_totals == []


@freeze_time("2016-04-01 23:00:00")
def test_populate_monthly_billing_updates_correct_month_in_bst(sample_template):
    yesterday = datetime.utcnow() - timedelta(days=1)
    apr_month_start = datetime(2016, 3, 31, 23)
    apr_month_end = datetime(2016, 4, 30, 22, 59, 59, 99999)
    create_rate(datetime(2016, 1, 1), 0.0123, 'sms')
    create_notification(template=sample_template, status='delivered', created_at=yesterday)
    populate_monthly_billing()

    monthly_billing = MonthlyBilling.query.order_by(MonthlyBilling.notification_type).all()

    assert len(monthly_billing) == 3

    assert monthly_billing[0].service_id == sample_template.service_id
    assert monthly_billing[0].start_date == apr_month_start
    assert monthly_billing[0].end_date == apr_month_end
    assert monthly_billing[0].notification_type == 'email'
    assert monthly_billing[0].monthly_totals == []

    assert monthly_billing[1].service_id == sample_template.service_id
    assert monthly_billing[1].start_date == apr_month_start
    assert monthly_billing[1].end_date == apr_month_end
    assert monthly_billing[1].notification_type == 'sms'
    assert monthly_billing[1].monthly_totals[0]['billing_units'] == 1
    assert monthly_billing[1].monthly_totals[0]['total_cost'] == 0.0123

    assert monthly_billing[2].service_id == sample_template.service_id
    assert monthly_billing[2].start_date == apr_month_start
    assert monthly_billing[2].end_date == apr_month_end
    assert monthly_billing[2].notification_type == 'letter'
    assert monthly_billing[2].monthly_totals == []


def test_run_letter_jobs(client, mocker, sample_letter_template):
    jobs = [create_job(template=sample_letter_template, job_status=JOB_STATUS_READY_TO_SEND),
            create_job(template=sample_letter_template, job_status=JOB_STATUS_READY_TO_SEND)]
    job_ids = [str(j.id) for j in jobs]
    mocker.patch(
        "app.celery.scheduled_tasks.dao_get_letter_job_ids_by_status",
        return_value=job_ids
    )
    mock_celery = mocker.patch("app.celery.tasks.notify_celery.send_task")

    run_letter_jobs()

    mock_celery.assert_called_once_with(name=TaskNames.DVLA_JOBS,
                                        args=(job_ids,),
                                        queue=QueueNames.PROCESS_FTP)


@freeze_time("2017-12-18 17:50")
def test_trigger_letter_pdfs_for_day(client, mocker, sample_letter_template):
    create_notification(template=sample_letter_template, created_at='2017-12-17 17:30:00')
    create_notification(template=sample_letter_template, created_at='2017-12-18 17:29:59')

    mock_celery = mocker.patch("app.celery.tasks.notify_celery.send_task")

    trigger_letter_pdfs_for_day()

    mock_celery.assert_called_once_with(name='collate-letter-pdfs-for-day',
                                        args=('2017-12-18',),
                                        queue=QueueNames.LETTERS)


@freeze_time("2017-12-18 17:50")
def test_trigger_letter_pdfs_for_day_send_task_not_called_if_no_notifications_for_day(
        client, mocker, notify_db_session):
    service = create_service(service_permissions=[LETTER_TYPE])
    template = create_template(service=service, template_type=LETTER_TYPE)
    create_notification(template=template, created_at='2017-12-15 17:30:00')

    mock_celery = mocker.patch("app.celery.tasks.notify_celery.send_task")

    trigger_letter_pdfs_for_day()

    assert not mock_celery.called


def test_run_letter_jobs_does_nothing_if_no_ready_jobs(client, mocker, sample_letter_template):
    create_job(sample_letter_template, job_status=JOB_STATUS_IN_PROGRESS)
    create_job(sample_letter_template, job_status=JOB_STATUS_SENT_TO_DVLA)
    mock_celery = mocker.patch("app.celery.tasks.notify_celery.send_task")

    run_letter_jobs()

    assert not mock_celery.called


def test_run_letter_api_notifications_triggers_ftp_task(client, mocker, notify_db_session):
    service = create_service(service_permissions=[LETTER_TYPE])
    template = create_template(service=service, template_type=LETTER_TYPE)
    notification = create_notification(template=template)
    file_contents_mock = mocker.patch(
        'app.celery.scheduled_tasks.create_dvla_file_contents_for_notifications',
        return_value='foo\nbar'
    )
    s3upload = mocker.patch('app.celery.scheduled_tasks.s3upload')
    mock_celery = mocker.patch('app.celery.tasks.notify_celery.send_task')
    filename = '2017-01-01T12:00:00-dvla-notifications.txt'

    with freeze_time('2017-01-01 12:00:00'):
        run_letter_api_notifications()

    assert notification.status == NOTIFICATION_PENDING
    file_contents_mock.assert_called_once_with([notification])
    s3upload.assert_called_once_with(
        # with trailing new line added
        filedata='foo\nbar\n',
        region='eu-west-1',
        bucket_name='test-dvla-letter-api-files',
        file_location=filename
    )
    mock_celery.assert_called_once_with(
        name=TaskNames.DVLA_NOTIFICATIONS,
        kwargs={'filename': filename},
        queue=QueueNames.PROCESS_FTP
    )


def test_run_letter_api_notifications_does_nothing_if_no_created_notifications(
    mocker,
    sample_letter_template,
    sample_letter_job,
    sample_api_key
):
    letter_job_notification = create_notification(
        sample_letter_template,
        job=sample_letter_job
    )
    create_notification(
        sample_letter_template,
        status=NOTIFICATION_PENDING,
        api_key=sample_api_key
    )
    test_api_key_notification = create_notification(
        sample_letter_template,
        key_type=KEY_TYPE_TEST
    )

    mock_celery = mocker.patch('app.celery.tasks.notify_celery.send_task')

    run_letter_api_notifications()

    assert not mock_celery.called
    assert letter_job_notification.status == NOTIFICATION_CREATED
    assert test_api_key_notification.status == NOTIFICATION_CREATED


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


def test_daily_stats_template_usage_by_month(notify_db, notify_db_session):
    notification_history = functools.partial(
        create_notification_history,
        notify_db,
        notify_db_session,
        status='delivered'
    )

    template_one = create_sample_template(notify_db, notify_db_session)
    template_two = create_sample_template(notify_db, notify_db_session)

    notification_history(created_at=datetime(2017, 10, 1), sample_template=template_one)
    notification_history(created_at=datetime(2016, 4, 1), sample_template=template_two)
    notification_history(created_at=datetime(2016, 4, 1), sample_template=template_two)
    notification_history(created_at=datetime.now(), sample_template=template_two)

    daily_stats_template_usage_by_month()

    result = db.session.query(
        StatsTemplateUsageByMonth
    ).order_by(
        StatsTemplateUsageByMonth.year,
        StatsTemplateUsageByMonth.month
    ).all()

    assert len(result) == 2

    assert result[0].template_id == template_two.id
    assert result[0].month == 4
    assert result[0].year == 2016
    assert result[0].count == 2

    assert result[1].template_id == template_one.id
    assert result[1].month == 10
    assert result[1].year == 2017
    assert result[1].count == 1


def test_daily_stats_template_usage_by_month_no_data():
    daily_stats_template_usage_by_month()

    results = db.session.query(StatsTemplateUsageByMonth).all()

    assert len(results) == 0


def test_daily_stats_template_usage_by_month_multiple_runs(notify_db, notify_db_session):
    notification_history = functools.partial(
        create_notification_history,
        notify_db,
        notify_db_session,
        status='delivered'
    )

    template_one = create_sample_template(notify_db, notify_db_session)
    template_two = create_sample_template(notify_db, notify_db_session)

    notification_history(created_at=datetime(2017, 11, 1), sample_template=template_one)
    notification_history(created_at=datetime(2016, 4, 1), sample_template=template_two)
    notification_history(created_at=datetime(2016, 4, 1), sample_template=template_two)
    notification_history(created_at=datetime.now(), sample_template=template_two)

    daily_stats_template_usage_by_month()

    template_three = create_sample_template(notify_db, notify_db_session)

    notification_history(created_at=datetime(2017, 10, 1), sample_template=template_three)
    notification_history(created_at=datetime(2017, 9, 1), sample_template=template_three)
    notification_history(created_at=datetime(2016, 4, 1), sample_template=template_two)
    notification_history(created_at=datetime(2016, 4, 1), sample_template=template_two)
    notification_history(created_at=datetime.now(), sample_template=template_two)

    daily_stats_template_usage_by_month()

    result = db.session.query(
        StatsTemplateUsageByMonth
    ).order_by(
        StatsTemplateUsageByMonth.year,
        StatsTemplateUsageByMonth.month
    ).all()

    assert len(result) == 4

    assert result[0].template_id == template_two.id
    assert result[0].month == 4
    assert result[0].year == 2016
    assert result[0].count == 4

    assert result[1].template_id == template_three.id
    assert result[1].month == 9
    assert result[1].year == 2017
    assert result[1].count == 1

    assert result[2].template_id == template_three.id
    assert result[2].month == 10
    assert result[2].year == 2017
    assert result[2].count == 1

    assert result[3].template_id == template_one.id
    assert result[3].month == 11
    assert result[3].year == 2017
    assert result[3].count == 1


def test_dao_fetch_monthly_historical_stats_by_template_null_template_id_not_counted(notify_db, notify_db_session):
    notification_history = functools.partial(
        create_notification_history,
        notify_db,
        notify_db_session,
        status='delivered'
    )

    template_one = create_sample_template(notify_db, notify_db_session, template_name='1')
    history = notification_history(created_at=datetime(2017, 2, 1), sample_template=template_one)

    NotificationHistory.query.filter(
        NotificationHistory.id == history.id
    ).update(
        {
            'template_id': None
        }
    )

    daily_stats_template_usage_by_month()

    result = db.session.query(
        StatsTemplateUsageByMonth
    ).all()

    assert len(result) == 0

    notification_history(created_at=datetime(2017, 2, 1), sample_template=template_one)

    daily_stats_template_usage_by_month()

    result = db.session.query(
        StatsTemplateUsageByMonth
    ).order_by(
        StatsTemplateUsageByMonth.year,
        StatsTemplateUsageByMonth.month
    ).all()

    assert len(result) == 1


def mock_s3_get_list_match(bucket_name, subfolder='', suffix='', last_modified=None):

    if subfolder == '2018-01-11/zips_sent':
        return ['NOTIFY.20180111175007.ZIP.TXT', 'NOTIFY.20180111175008.ZIP.TXT']
    if subfolder == 'root/dispatch':
        return ['root/dispatch/NOTIFY.20180111175733.ACK.txt']


def mock_s3_get_list_diff(bucket_name, subfolder='', suffix='', last_modified=None):
    if subfolder == '2018-01-11/zips_sent':
        return ['NOTIFY.20180111175007.ZIP.TXT', 'NOTIFY.20180111175008.ZIP.TXT', 'NOTIFY.20180111175009.ZIP.TXT',
                'NOTIFY.20180111175010.ZIP.TXT']
    if subfolder == 'root/dispatch':
        return ['root/dispatch/NOTIFY.20180111175733.ACK.txt']


@freeze_time('2018-01-11T23:00:00')
def test_letter_not_raise_alert_if_ack_files_match_zip_list(mocker, notify_db):
    mock_file_list = mocker.patch("app.aws.s3.get_list_of_files_by_suffix", side_effect=mock_s3_get_list_match)
    mock_get_file = mocker.patch("app.aws.s3.get_s3_file",
                                 return_value='NOTIFY.20180111175007.ZIP|20180111175733\n'
                                              'NOTIFY.20180111175008.ZIP|20180111175734')

    letter_raise_alert_if_no_ack_file_for_zip()

    yesterday = datetime.now(tz=pytz.utc) - timedelta(days=1)   # Datatime format on AWS
    subfoldername = datetime.utcnow().strftime('%Y-%m-%d') + '/zips_sent'
    assert mock_file_list.call_count == 2
    assert mock_file_list.call_args_list == [
        call(bucket_name=current_app.config['LETTERS_PDF_BUCKET_NAME'], subfolder=subfoldername, suffix='.TXT'),
        call(bucket_name=current_app.config['DVLA_RESPONSE_BUCKET_NAME'], subfolder='root/dispatch',
             suffix='.ACK.txt', last_modified=yesterday),
    ]
    assert mock_get_file.call_count == 1


@freeze_time('2018-01-11T23:00:00')
def test_letter_raise_alert_if_ack_files_not_match_zip_list(mocker, notify_db):
    mock_file_list = mocker.patch("app.aws.s3.get_list_of_files_by_suffix", side_effect=mock_s3_get_list_diff)
    mock_get_file = mocker.patch("app.aws.s3.get_s3_file",
                                 return_value='NOTIFY.20180111175007.ZIP|20180111175733\n'
                                              'NOTIFY.20180111175008.ZIP|20180111175734')
    mock_deskpro = mocker.patch("app.celery.scheduled_tasks.deskpro_client.create_ticket")

    letter_raise_alert_if_no_ack_file_for_zip()

    assert mock_file_list.call_count == 2
    assert mock_get_file.call_count == 1

    deskpro_message = "Letter ack file does not contains all zip files sent. " \
                      "Missing ack for zip files: {}, " \
                      "pdf bucket: {}, subfolder: {}, " \
                      "ack bucket: {}".format(str(['NOTIFY.20180111175009.ZIP', 'NOTIFY.20180111175010.ZIP']),
                                              current_app.config['LETTERS_PDF_BUCKET_NAME'],
                                              datetime.utcnow().strftime('%Y-%m-%d') + '/zips_sent',
                                              current_app.config['DVLA_RESPONSE_BUCKET_NAME'])

    mock_deskpro.assert_called_once_with(
        subject="Letter acknowledge error",
        message=deskpro_message,
        ticket_type='alert'
    )


@freeze_time('2018-01-11T23:00:00')
def test_letter_not_raise_alert_if_no_files_do_not_cause_error(mocker, notify_db):
    mock_file_list = mocker.patch("app.aws.s3.get_list_of_files_by_suffix", side_effect=None)
    mock_get_file = mocker.patch("app.aws.s3.get_s3_file",
                                 return_value='NOTIFY.20180111175007.ZIP|20180111175733\n'
                                              'NOTIFY.20180111175008.ZIP|20180111175734')

    letter_raise_alert_if_no_ack_file_for_zip()

    assert mock_file_list.call_count == 2
    assert mock_get_file.call_count == 0
