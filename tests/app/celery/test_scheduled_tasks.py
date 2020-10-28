import uuid
from datetime import datetime, timedelta
from unittest.mock import call

import pytest
from collections import namedtuple
from freezegun import freeze_time
from mock import mock

from app.celery import scheduled_tasks
from app.celery.scheduled_tasks import (
    check_job_status,
    delete_invitations,
    delete_verify_codes,
    run_scheduled_jobs,
    replay_created_notifications,
    check_precompiled_letter_state,
    check_templated_letter_state,
    check_for_missing_rows_in_completed_jobs,
    check_for_services_with_high_failure_rates_or_sending_to_tv_numbers,
    switch_current_sms_provider_on_slow_delivery,
)
from app.config import QueueNames, Config
from app.dao.jobs_dao import dao_get_job_by_id
from app.dao.provider_details_dao import get_provider_details_by_identifier
from app.models import (
    JOB_STATUS_IN_PROGRESS,
    JOB_STATUS_ERROR,
    JOB_STATUS_FINISHED,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_PENDING_VIRUS_CHECK,
)
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


def test_should_call_delete_codes_on_delete_verify_codes_task(notify_db_session, mocker):
    mocker.patch('app.celery.scheduled_tasks.delete_codes_older_created_more_than_a_day_ago')
    delete_verify_codes()
    assert scheduled_tasks.delete_codes_older_created_more_than_a_day_ago.call_count == 1


def test_should_call_delete_invotations_on_delete_invitations_task(notify_db_session, mocker):
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


@freeze_time('2017-05-01 14:00:00')
def test_switch_current_sms_provider_on_slow_delivery_switches_when_one_provider_is_slow(
    mocker,
    restore_provider_details,
):
    is_slow_dict = {'mmg': False, 'firetext': True}
    mock_is_slow = mocker.patch('app.celery.scheduled_tasks.is_delivery_slow_for_providers', return_value=is_slow_dict)
    mock_reduce = mocker.patch('app.celery.scheduled_tasks.dao_reduce_sms_provider_priority')
    # updated_at times are older than the 10 minute window
    get_provider_details_by_identifier('mmg').updated_at = datetime(2017, 5, 1, 13, 49)
    get_provider_details_by_identifier('firetext').updated_at = None

    switch_current_sms_provider_on_slow_delivery()

    mock_is_slow.assert_called_once_with(
        threshold=0.3,
        created_at=datetime(2017, 5, 1, 13, 50),
        delivery_time=timedelta(minutes=4)
    )
    mock_reduce.assert_called_once_with('firetext', time_threshold=timedelta(minutes=10))


@freeze_time('2017-05-01 14:00:00')
@pytest.mark.parametrize('is_slow_dict', [
    {'mmg': False, 'firetext': False},
    {'mmg': True, 'firetext': True},
])
def test_switch_current_sms_provider_on_slow_delivery_does_nothing_if_no_need(
    mocker,
    restore_provider_details,
    is_slow_dict
):
    mocker.patch('app.celery.scheduled_tasks.is_delivery_slow_for_providers', return_value=is_slow_dict)
    mock_reduce = mocker.patch('app.celery.scheduled_tasks.dao_reduce_sms_provider_priority')
    get_provider_details_by_identifier('mmg').updated_at = datetime(2017, 5, 1, 13, 51)

    switch_current_sms_provider_on_slow_delivery()

    assert mock_reduce.called is False


def test_check_job_status_task_calls_process_incomplete_jobs(mocker, sample_template):
    mock_celery = mocker.patch('app.celery.tasks.process_incomplete_jobs.apply_async')
    job = create_job(template=sample_template, notification_count=3,
                     created_at=datetime.utcnow() - timedelta(minutes=31),
                     processing_started=datetime.utcnow() - timedelta(minutes=31),
                     job_status=JOB_STATUS_IN_PROGRESS)
    create_notification(template=sample_template, job=job)
    check_job_status()

    mock_celery.assert_called_once_with(
        [[str(job.id)]],
        queue=QueueNames.JOBS
    )


def test_check_job_status_task_calls_process_incomplete_jobs_when_scheduled_job_is_not_complete(
    mocker, sample_template
):
    mock_celery = mocker.patch('app.celery.tasks.process_incomplete_jobs.apply_async')
    job = create_job(template=sample_template, notification_count=3,
                     created_at=datetime.utcnow() - timedelta(hours=2),
                     scheduled_for=datetime.utcnow() - timedelta(minutes=31),
                     processing_started=datetime.utcnow() - timedelta(minutes=31),
                     job_status=JOB_STATUS_IN_PROGRESS)
    check_job_status()

    mock_celery.assert_called_once_with(
        [[str(job.id)]],
        queue=QueueNames.JOBS
    )


def test_check_job_status_task_calls_process_incomplete_jobs_for_multiple_jobs(mocker, sample_template):
    mock_celery = mocker.patch('app.celery.tasks.process_incomplete_jobs.apply_async')
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
    check_job_status()

    mock_celery.assert_called_once_with(
        [[str(job.id), str(job_2.id)]],
        queue=QueueNames.JOBS
    )


def test_check_job_status_task_only_sends_old_tasks(mocker, sample_template):
    mock_celery = mocker.patch('app.celery.tasks.process_incomplete_jobs.apply_async')
    job = create_job(
        template=sample_template,
        notification_count=3,
        created_at=datetime.utcnow() - timedelta(hours=2),
        scheduled_for=datetime.utcnow() - timedelta(minutes=31),
        processing_started=datetime.utcnow() - timedelta(minutes=31),
        job_status=JOB_STATUS_IN_PROGRESS
    )
    create_job(
        template=sample_template,
        notification_count=3,
        created_at=datetime.utcnow() - timedelta(minutes=31),
        processing_started=datetime.utcnow() - timedelta(minutes=29),
        job_status=JOB_STATUS_IN_PROGRESS
    )
    check_job_status()

    # job 2 not in celery task
    mock_celery.assert_called_once_with(
        [[str(job.id)]],
        queue=QueueNames.JOBS
    )


def test_check_job_status_task_sets_jobs_to_error(mocker, sample_template):
    mock_celery = mocker.patch('app.celery.tasks.process_incomplete_jobs.apply_async')
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
    check_job_status()

    # job 2 not in celery task
    mock_celery.assert_called_once_with(
        [[str(job.id)]],
        queue=QueueNames.JOBS
    )
    assert job.job_status == JOB_STATUS_ERROR
    assert job_2.job_status == JOB_STATUS_IN_PROGRESS


def test_replay_created_notifications(notify_db_session, sample_service, mocker):
    email_delivery_queue = mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    sms_delivery_queue = mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')

    sms_template = create_template(service=sample_service, template_type='sms')
    email_template = create_template(service=sample_service, template_type='email')
    older_than = (60 * 60) + (60 * 15)  # 1 hour 15 minutes
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


def test_replay_created_notifications_get_pdf_for_templated_letter_tasks_for_letters_not_ready_to_send(
        sample_letter_template, mocker
):
    mock_task = mocker.patch('app.celery.scheduled_tasks.get_pdf_for_templated_letter.apply_async')
    create_notification(template=sample_letter_template, billable_units=0,
                        created_at=datetime.utcnow() - timedelta(hours=4))

    create_notification(template=sample_letter_template, billable_units=0,
                        created_at=datetime.utcnow() - timedelta(minutes=20))
    notification_1 = create_notification(template=sample_letter_template, billable_units=0,
                                         created_at=datetime.utcnow() - timedelta(hours=1, minutes=20))
    notification_2 = create_notification(template=sample_letter_template, billable_units=0,
                                         created_at=datetime.utcnow() - timedelta(hours=5))

    replay_created_notifications()

    calls = [call([str(notification_1.id)], queue=QueueNames.CREATE_LETTERS_PDF),
             call([str(notification_2.id)], queue=QueueNames.CREATE_LETTERS_PDF),
             ]
    mock_task.assert_has_calls(calls, any_order=True)


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
    notification_1 = create_notification(template=sample_letter_template,
                                         status=NOTIFICATION_PENDING_VIRUS_CHECK,
                                         created_at=datetime.utcnow() - timedelta(seconds=5401),
                                         reference='one')
    notification_2 = create_notification(template=sample_letter_template,
                                         status=NOTIFICATION_PENDING_VIRUS_CHECK,
                                         created_at=datetime.utcnow() - timedelta(seconds=70000),
                                         reference='two')

    check_precompiled_letter_state()

    id_references = sorted([(str(notification_1.id), notification_1.reference),
                            (str(notification_2.id), notification_2.reference)])

    message = """2 precompiled letters have been pending-virus-check for over 90 minutes. Follow runbook to resolve:
            https://github.com/alphagov/notifications-manuals/wiki/Support-Runbook#Deal-with-letter-pending-virus-scan-for-90-minutes.
            Notifications: {}""".format(id_references)

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

    noti_1 = create_notification(template=sample_letter_template, created_at=datetime(2019, 5, 1, 12, 0))
    noti_2 = create_notification(template=sample_letter_template, created_at=datetime(2019, 5, 29, 16, 29))
    create_notification(template=sample_letter_template, created_at=datetime(2019, 5, 29, 16, 30))
    create_notification(template=sample_letter_template, created_at=datetime(2019, 5, 29, 17, 29))
    create_notification(template=sample_letter_template, status='delivered', created_at=datetime(2019, 5, 28, 10, 0))
    create_notification(template=sample_letter_template, created_at=datetime(2019, 5, 30, 10, 0))

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
    mock_create_ticket = mocker.patch('app.celery.scheduled_tasks.zendesk_client.create_ticket')

    noti_1 = create_notification(template=sample_letter_template, created_at=datetime(2018, 12, 1, 12, 0))
    noti_2 = create_notification(template=sample_letter_template, created_at=datetime(2019, 1, 29, 17, 29))
    create_notification(template=sample_letter_template, created_at=datetime(2019, 1, 29, 17, 30))
    create_notification(template=sample_letter_template, created_at=datetime(2019, 1, 29, 18, 29))
    create_notification(template=sample_letter_template, status='delivered', created_at=datetime(2019, 1, 29, 10, 0))
    create_notification(template=sample_letter_template, created_at=datetime(2019, 1, 30, 10, 0))

    check_templated_letter_state()

    message = "2 letters were created before 17.30 yesterday and still have 'created' status. " \
              "Notifications: ['{}', '{}']".format(noti_1.id, noti_2.id)

    mock_logger.assert_called_once_with(message)
    mock_create_ticket.assert_called_with(
        message=message,
        subject="[test] Letters still in 'created' status",
        ticket_type='incident'
    )


@pytest.mark.parametrize('offset', (
    timedelta(days=1),
    pytest.param(timedelta(hours=23, minutes=59), marks=pytest.mark.xfail),
    pytest.param(timedelta(minutes=20), marks=pytest.mark.xfail),
    timedelta(minutes=19),
))
def test_check_for_missing_rows_in_completed_jobs_ignores_old_and_new_jobs(
    mocker,
    sample_email_template,
    offset,
):
    mocker.patch('app.celery.tasks.s3.get_job_and_metadata_from_s3',
                 return_value=(load_example_csv('multiple_email'), {"sender_id": None}))
    mocker.patch('app.encryption.encrypt', return_value="something_encrypted")
    process_row = mocker.patch('app.celery.scheduled_tasks.process_row')

    job = create_job(
        template=sample_email_template,
        notification_count=5,
        job_status=JOB_STATUS_FINISHED,
        processing_finished=datetime.utcnow() - offset,
    )
    for i in range(0, 4):
        create_notification(job=job, job_row_number=i)

    check_for_missing_rows_in_completed_jobs()

    assert process_row.called is False


def test_check_for_missing_rows_in_completed_jobs(mocker, sample_email_template):
    mocker.patch('app.celery.tasks.s3.get_job_and_metadata_from_s3',
                 return_value=(load_example_csv('multiple_email'), {"sender_id": None}))
    mocker.patch('app.encryption.encrypt', return_value="something_encrypted")
    process_row = mocker.patch('app.celery.scheduled_tasks.process_row')

    job = create_job(template=sample_email_template,
                     notification_count=5,
                     job_status=JOB_STATUS_FINISHED,
                     processing_finished=datetime.utcnow() - timedelta(minutes=20))
    for i in range(0, 4):
        create_notification(job=job, job_row_number=i)

    check_for_missing_rows_in_completed_jobs()

    process_row.assert_called_once_with(
        mock.ANY, mock.ANY, job, job.service, sender_id=None
    )


def test_check_for_missing_rows_in_completed_jobs_calls_save_email(mocker, sample_email_template):
    mocker.patch('app.celery.tasks.s3.get_job_and_metadata_from_s3',
                 return_value=(load_example_csv('multiple_email'), {'sender_id': None}))
    save_email_task = mocker.patch('app.celery.tasks.save_email.apply_async')
    mocker.patch('app.encryption.encrypt', return_value="something_encrypted")
    mocker.patch('app.celery.tasks.create_uuid', return_value='uuid')

    job = create_job(template=sample_email_template,
                     notification_count=5,
                     job_status=JOB_STATUS_FINISHED,
                     processing_finished=datetime.utcnow() - timedelta(minutes=20))
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


def test_check_for_missing_rows_in_completed_jobs_uses_sender_id(mocker, sample_email_template, fake_uuid):
    mocker.patch('app.celery.tasks.s3.get_job_and_metadata_from_s3',
                 return_value=(load_example_csv('multiple_email'), {'sender_id': fake_uuid}))
    mock_process_row = mocker.patch('app.celery.scheduled_tasks.process_row')

    job = create_job(template=sample_email_template,
                     notification_count=5,
                     job_status=JOB_STATUS_FINISHED,
                     processing_finished=datetime.utcnow() - timedelta(minutes=20))
    for i in range(0, 4):
        create_notification(job=job, job_row_number=i)

    check_for_missing_rows_in_completed_jobs()
    mock_process_row.assert_called_once_with(
        mock.ANY, mock.ANY, job, job.service, sender_id=fake_uuid
    )


MockServicesSendingToTVNumbers = namedtuple(
    'ServicesSendingToTVNumbers',
    [
        'service_id',
        'notification_count',
    ]
)
MockServicesWithHighFailureRate = namedtuple(
    'ServicesWithHighFailureRate',
    [
        'service_id',
        'permanent_failure_rate',
    ]
)


@pytest.mark.parametrize("failure_rates, sms_to_tv_numbers, expected_message", [
    [
        [MockServicesWithHighFailureRate("123", 0.3)],
        [],
        "1 service(s) have had high permanent-failure rates for sms messages in last "
        "24 hours:\nservice: {}/services/{} failure rate: 0.3,\n".format(
            Config.ADMIN_BASE_URL, "123"
        )
    ],
    [
        [],
        [MockServicesSendingToTVNumbers("123", 300)],
        "1 service(s) have sent over 500 sms messages to tv numbers in last 24 hours:\n"
        "service: {}/services/{} count of sms to tv numbers: 300,\n".format(
            Config.ADMIN_BASE_URL, "123"
        )
    ]
])
def test_check_for_services_with_high_failure_rates_or_sending_to_tv_numbers(
    mocker, notify_db_session, failure_rates, sms_to_tv_numbers, expected_message
):
    mock_logger = mocker.patch('app.celery.tasks.current_app.logger.warning')
    mock_create_ticket = mocker.patch('app.celery.scheduled_tasks.zendesk_client.create_ticket')
    mock_failure_rates = mocker.patch(
        'app.celery.scheduled_tasks.dao_find_services_with_high_failure_rates', return_value=failure_rates
    )
    mock_sms_to_tv_numbers = mocker.patch(
        'app.celery.scheduled_tasks.dao_find_services_sending_to_tv_numbers', return_value=sms_to_tv_numbers
    )

    zendesk_actions = "\nYou can find instructions for this ticket in our manual:\nhttps://github.com/alphagov/notifications-manuals/wiki/Support-Runbook#Deal-with-services-with-high-failure-rates-or-sending-sms-to-tv-numbers"  # noqa

    check_for_services_with_high_failure_rates_or_sending_to_tv_numbers()

    assert mock_failure_rates.called
    assert mock_sms_to_tv_numbers.called
    mock_logger.assert_called_once_with(expected_message)
    mock_create_ticket.assert_called_with(
        message=expected_message + zendesk_actions,
        subject="[test] High failure rates for sms spotted for services",
        ticket_type='incident'
    )


def test_send_canary_to_cbc_proxy_invokes_cbc_proxy_client(
    mocker,
):
    mock_send_canary = mocker.patch(
        'app.cbc_proxy_client.send_canary',
    )

    scheduled_tasks.send_canary_to_cbc_proxy()

    mock_send_canary.assert_called
    # the 0th argument of the call to send_canary
    identifier = mock_send_canary.mock_calls[0][1][0]

    try:
        uuid.UUID(identifier)
    except BaseException:
        pytest.fail(f"{identifier} is not a valid uuid")


def test_trigger_link_tests_invokes_cbc_proxy_client(
    mocker,
):
    mock_send_link_test = mocker.patch(
        'app.cbc_proxy_client.send_link_test',
    )

    scheduled_tasks.trigger_link_tests()

    mock_send_link_test.assert_called
    # the 0th argument of the call to send_link_test
    identifier = mock_send_link_test.mock_calls[0][1][0]

    try:
        uuid.UUID(identifier)
    except BaseException:
        pytest.fail(f"{identifier} is not a valid uuid")
