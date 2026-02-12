import uuid
from collections import namedtuple
from datetime import datetime, timedelta
from unittest import mock
from unittest.mock import ANY, call

import dateutil
import pytest
from celery.exceptions import Retry
from freezegun import freeze_time
from notifications_utils.clients.zendesk.zendesk_client import (
    NotifySupportTicket,
    NotifySupportTicketAttachment,
    NotifySupportTicketComment,
    NotifySupportTicketStatus,
    NotifyTicketType,
)
from redis.exceptions import LockError

from app.celery import scheduled_tasks
from app.celery.letters_pdf_tasks import get_pdf_for_templated_letter
from app.celery.provider_tasks import deliver_email, deliver_sms
from app.celery.scheduled_tasks import (
    _check_slow_text_message_delivery_reports_and_raise_error_if_needed,
    change_dvla_api_key,
    change_dvla_password,
    check_for_low_available_inbound_sms_numbers,
    check_for_missing_rows_in_completed_jobs,
    check_for_services_with_high_failure_rates_or_sending_to_tv_numbers,
    check_if_letters_still_in_created,
    check_if_letters_still_pending_virus_check,
    check_job_status,
    delete_invitations,
    delete_old_records_from_events_table,
    delete_verify_codes,
    generate_sms_delivery_stats,
    populate_annual_billing,
    replay_created_notifications,
    run_populate_annual_billing,
    run_scheduled_jobs,
    switch_current_sms_provider_on_slow_delivery,
    update_status_of_fully_processed_jobs,
    weekly_dwp_report,
    weekly_user_research_email,
    zendesk_new_email_branding_report,
)
from app.celery.tasks import process_incomplete_jobs, process_job, save_email
from app.clients.letter.dvla import (
    DvlaNonRetryableException,
    DvlaThrottlingException,
)
from app.config import Config, QueueNames, TaskNames
from app.constants import (
    JOB_STATUS_ERROR,
    JOB_STATUS_FINISHED,
    JOB_STATUS_FINISHED_ALL_NOTIFICATIONS_CREATED,
    JOB_STATUS_IN_PROGRESS,
    JOB_STATUS_PENDING,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_PENDING_VIRUS_CHECK,
)
from app.dao.annual_billing_dao import set_default_free_allowance_for_service
from app.dao.jobs_dao import dao_get_job_by_id
from app.dao.notifications_dao import SlowProviderDeliveryReport
from app.dao.provider_details_dao import get_provider_details_by_identifier
from app.models import Event, InboundNumber, Notification
from tests.app import load_example_csv
from tests.app.db import (
    create_email_branding,
    create_job,
    create_notification,
    create_organisation,
    create_template,
    create_user,
)
from tests.conftest import set_config, set_config_values


def test_should_call_delete_codes_on_delete_verify_codes_task(notify_db_session, mocker):
    mocker.patch("app.celery.scheduled_tasks.delete_codes_older_created_more_than_a_day_ago")
    delete_verify_codes()
    assert scheduled_tasks.delete_codes_older_created_more_than_a_day_ago.call_count == 1


def test_should_call_delete_invotations_on_delete_invitations_task(notify_db_session, mocker):
    mocker.patch("app.celery.scheduled_tasks.delete_invitations_created_more_than_two_days_ago")
    delete_invitations()
    assert scheduled_tasks.delete_invitations_created_more_than_two_days_ago.call_count == 1


def test_should_update_scheduled_jobs_and_put_on_queue(mock_celery_task, sample_template):
    mocked = mock_celery_task(process_job)

    one_minute_in_the_past = datetime.utcnow() - timedelta(minutes=1)
    job = create_job(sample_template, job_status="scheduled", scheduled_for=one_minute_in_the_past)

    run_scheduled_jobs()

    updated_job = dao_get_job_by_id(job.id)
    assert updated_job.job_status == "pending"
    mocked.assert_called_with([str(job.id)], queue="job-tasks")


def test_should_update_all_scheduled_jobs_and_put_on_queue(sample_template, mock_celery_task):
    mocked = mock_celery_task(process_job)

    one_minute_in_the_past = datetime.utcnow() - timedelta(minutes=1)
    ten_minutes_in_the_past = datetime.utcnow() - timedelta(minutes=10)
    twenty_minutes_in_the_past = datetime.utcnow() - timedelta(minutes=20)
    job_1 = create_job(sample_template, job_status="scheduled", scheduled_for=one_minute_in_the_past)
    job_2 = create_job(sample_template, job_status="scheduled", scheduled_for=ten_minutes_in_the_past)
    job_3 = create_job(sample_template, job_status="scheduled", scheduled_for=twenty_minutes_in_the_past)

    run_scheduled_jobs()

    assert dao_get_job_by_id(job_1.id).job_status == "pending"
    assert dao_get_job_by_id(job_2.id).job_status == "pending"
    assert dao_get_job_by_id(job_2.id).job_status == "pending"

    mocked.assert_has_calls(
        [
            call([str(job_3.id)], queue="job-tasks"),
            call([str(job_2.id)], queue="job-tasks"),
            call([str(job_1.id)], queue="job-tasks"),
        ]
    )


@freeze_time("2017-05-01 14:00:00")
def test_switch_current_sms_provider_on_slow_delivery_switches_when_one_provider_is_slow(
    mocker,
    restore_provider_details,
):
    is_slow_dict = {"mmg": False, "firetext": True}
    mock_is_slow = mocker.patch("app.celery.scheduled_tasks.is_delivery_slow_for_providers", return_value=is_slow_dict)
    mock_reduce = mocker.patch("app.celery.scheduled_tasks.dao_reduce_sms_provider_priority")
    # updated_at times are older than the 10 minute window
    get_provider_details_by_identifier("mmg").updated_at = datetime(2017, 5, 1, 13, 49)
    get_provider_details_by_identifier("firetext").updated_at = None

    switch_current_sms_provider_on_slow_delivery()

    mock_is_slow.assert_called_once_with(created_within_minutes=15, delivered_within_minutes=5, threshold=0.15)
    mock_reduce.assert_called_once_with("firetext", time_threshold=timedelta(minutes=5))


@freeze_time("2017-05-01 14:00:00")
@pytest.mark.parametrize(
    "is_slow_dict",
    [
        {"mmg": False, "firetext": False},
        {"mmg": True, "firetext": True},
    ],
)
def test_switch_current_sms_provider_on_slow_delivery_does_nothing_if_no_need(
    mocker, restore_provider_details, is_slow_dict
):
    mocker.patch("app.celery.scheduled_tasks.is_delivery_slow_for_providers", return_value=is_slow_dict)
    mock_reduce = mocker.patch("app.celery.scheduled_tasks.dao_reduce_sms_provider_priority")
    get_provider_details_by_identifier("mmg").updated_at = datetime(2017, 5, 1, 13, 51)

    switch_current_sms_provider_on_slow_delivery()

    assert mock_reduce.called is False


@pytest.mark.parametrize(
    "slow_delivery_config_option, expect_check_slow_delivery",
    (
        (
            False,
            False,
        ),
        (
            True,
            True,
        ),
    ),
)
def test_generate_sms_delivery_stats(slow_delivery_config_option, expect_check_slow_delivery, mocker, notify_api):
    slow_delivery_reports = [
        SlowProviderDeliveryReport(provider="mmg", slow_ratio=0.4, slow_notifications=40, total_notifications=100),
        SlowProviderDeliveryReport(provider="firetext", slow_ratio=0.8, slow_notifications=80, total_notifications=100),
    ]
    mocker.patch(
        "app.celery.scheduled_tasks.get_slow_text_message_delivery_reports_by_provider",
        return_value=slow_delivery_reports,
    )
    mock_statsd = mocker.patch("app.celery.scheduled_tasks.statsd_client.gauge")
    mock_check_slow_delivery = mocker.patch(
        "app.celery.scheduled_tasks._check_slow_text_message_delivery_reports_and_raise_error_if_needed"
    )

    with set_config(notify_api, "CHECK_SLOW_TEXT_MESSAGE_DELIVERY", slow_delivery_config_option):
        generate_sms_delivery_stats()

    calls = [
        call("slow-delivery.mmg.delivered-within-minutes.1.ratio", 0.4),
        call("slow-delivery.mmg.delivered-within-minutes.5.ratio", 0.4),
        call("slow-delivery.mmg.delivered-within-minutes.10.ratio", 0.4),
        call("slow-delivery.firetext.delivered-within-minutes.1.ratio", 0.8),
        call("slow-delivery.firetext.delivered-within-minutes.5.ratio", 0.8),
        call("slow-delivery.firetext.delivered-within-minutes.10.ratio", 0.8),
        call("slow-delivery.sms.delivered-within-minutes.1.ratio", 0.6),
        call("slow-delivery.sms.delivered-within-minutes.5.ratio", 0.6),
        call("slow-delivery.sms.delivered-within-minutes.10.ratio", 0.6),
    ]
    mock_statsd.assert_has_calls(calls, any_order=True)

    assert mock_check_slow_delivery.call_args_list == (
        [mocker.call(slow_delivery_reports)] if expect_check_slow_delivery else []
    )


@pytest.mark.parametrize("consecutive_failures,should_log", ((1, False), (9, False), (10, True)))
def test_check_slow_text_message_delivery_reports_and_raise_error_if_needed(
    mocker, caplog, notify_api, consecutive_failures, should_log
):
    mock_incr = mocker.patch("app.celery.scheduled_tasks.redis_store.incr")
    mock_set = mocker.patch("app.celery.scheduled_tasks.redis_store.set")
    mock_incr.return_value = 1

    with set_config(notify_api, "REDIS_ENABLED", True):
        # Below 10% threshold, should not trigger logs and should set redis cache key to 0
        for _ in range(consecutive_failures):
            mock_incr.return_value = consecutive_failures
            mock_set.reset_mock()
            _check_slow_text_message_delivery_reports_and_raise_error_if_needed(
                [
                    SlowProviderDeliveryReport(
                        provider="mmg", slow_ratio=0.10, slow_notifications=10, total_notifications=100
                    ),
                    SlowProviderDeliveryReport(
                        provider="firetext", slow_ratio=0.09, slow_notifications=9, total_notifications=100
                    ),
                ]
            )
            assert (
                "Over 10% of text messages sent in the last 25 minutes have taken over 5 minutes to deliver."
                not in caplog.messages
            )
            assert mock_set.call_args_list == [mocker.call("slow-sms-delivery:number-of-times-over-threshold", 0)]

        # At 10%+, should increment redis and log an error when it's the fifth consecutive call.
        for _ in range(consecutive_failures):
            mock_incr.reset_mock()
            mock_incr.return_value = consecutive_failures
            _check_slow_text_message_delivery_reports_and_raise_error_if_needed(
                [
                    SlowProviderDeliveryReport(
                        provider="mmg", slow_ratio=0.10, slow_notifications=10, total_notifications=100
                    ),
                    SlowProviderDeliveryReport(
                        provider="firetext", slow_ratio=0.10, slow_notifications=10, total_notifications=100
                    ),
                ]
            )
            assert (
                "Over 10% of text messages sent in the last 25 minutes have taken over 5 minutes to deliver."
                in caplog.messages
            ) is should_log
            assert mock_incr.call_args_list == [mocker.call("slow-sms-delivery:number-of-times-over-threshold")]


def test_check_job_status_task_calls_process_incomplete_jobs(mock_celery_task, sample_template):
    mock_celery = mock_celery_task(process_incomplete_jobs)
    job = create_job(
        template=sample_template,
        notification_count=3,
        created_at=datetime.utcnow() - timedelta(minutes=31),
        processing_started=datetime.utcnow() - timedelta(minutes=31),
        job_status=JOB_STATUS_IN_PROGRESS,
    )
    create_notification(template=sample_template, job=job)
    check_job_status()

    mock_celery.assert_called_once_with([[str(job.id)]], queue=QueueNames.JOBS)


def test_check_job_status_task_calls_process_incomplete_jobs_when_scheduled_job_is_not_complete(
    mock_celery_task, sample_template
):
    mock_celery = mock_celery_task(process_incomplete_jobs)
    job = create_job(
        template=sample_template,
        notification_count=3,
        created_at=datetime.utcnow() - timedelta(hours=2),
        scheduled_for=datetime.utcnow() - timedelta(minutes=31),
        processing_started=datetime.utcnow() - timedelta(minutes=31),
        job_status=JOB_STATUS_IN_PROGRESS,
    )
    check_job_status()

    mock_celery.assert_called_once_with([[str(job.id)]], queue=QueueNames.JOBS)


def test_check_job_status_task_calls_process_incomplete_jobs_for_pending_scheduled_jobs(
    mock_celery_task, sample_template
):
    mock_celery = mock_celery_task(process_incomplete_jobs)
    job = create_job(
        template=sample_template,
        notification_count=3,
        created_at=datetime.utcnow() - timedelta(hours=2),
        scheduled_for=datetime.utcnow() - timedelta(minutes=31),
        job_status=JOB_STATUS_PENDING,
    )

    check_job_status()

    mock_celery.assert_called_once_with([[str(job.id)]], queue=QueueNames.JOBS)


def test_check_job_status_task_does_not_call_process_incomplete_jobs_for_non_scheduled_pending_jobs(
    mock_celery_task,
    sample_template,
):
    mock_celery = mock_celery_task(process_incomplete_jobs)
    create_job(
        template=sample_template,
        notification_count=3,
        created_at=datetime.utcnow() - timedelta(hours=2),
        job_status=JOB_STATUS_PENDING,
    )
    check_job_status()

    assert not mock_celery.called


def test_check_job_status_task_calls_process_incomplete_jobs_for_multiple_jobs(mock_celery_task, sample_template):
    mock_celery = mock_celery_task(process_incomplete_jobs)
    job = create_job(
        template=sample_template,
        notification_count=3,
        created_at=datetime.utcnow() - timedelta(hours=2),
        scheduled_for=datetime.utcnow() - timedelta(minutes=31),
        processing_started=datetime.utcnow() - timedelta(minutes=31),
        job_status=JOB_STATUS_IN_PROGRESS,
    )
    job_2 = create_job(
        template=sample_template,
        notification_count=3,
        created_at=datetime.utcnow() - timedelta(hours=2),
        scheduled_for=datetime.utcnow() - timedelta(minutes=31),
        processing_started=datetime.utcnow() - timedelta(minutes=31),
        job_status=JOB_STATUS_IN_PROGRESS,
    )
    check_job_status()

    mock_celery.assert_called_once_with([[str(job.id), str(job_2.id)]], queue=QueueNames.JOBS)


def test_check_job_status_task_only_sends_old_tasks(mock_celery_task, sample_template):
    mock_celery = mock_celery_task(process_incomplete_jobs)
    job = create_job(
        template=sample_template,
        notification_count=3,
        created_at=datetime.utcnow() - timedelta(hours=2),
        scheduled_for=datetime.utcnow() - timedelta(minutes=31),
        processing_started=datetime.utcnow() - timedelta(minutes=31),
        job_status=JOB_STATUS_IN_PROGRESS,
    )
    create_job(
        template=sample_template,
        notification_count=3,
        created_at=datetime.utcnow() - timedelta(minutes=31),
        processing_started=datetime.utcnow() - timedelta(minutes=29),
        job_status=JOB_STATUS_IN_PROGRESS,
    )
    create_job(
        template=sample_template,
        notification_count=3,
        created_at=datetime.utcnow() - timedelta(minutes=50),
        scheduled_for=datetime.utcnow() - timedelta(minutes=29),
        job_status=JOB_STATUS_PENDING,
    )
    check_job_status()

    # jobs 2 and 3 were created less than 30 minutes ago, so are not sent to Celery task
    mock_celery.assert_called_once_with([[str(job.id)]], queue=QueueNames.JOBS)


def test_check_job_status_task_sets_jobs_to_error(mock_celery_task, sample_template):
    mock_celery = mock_celery_task(process_incomplete_jobs)
    job = create_job(
        template=sample_template,
        notification_count=3,
        created_at=datetime.utcnow() - timedelta(hours=2),
        scheduled_for=datetime.utcnow() - timedelta(minutes=31),
        processing_started=datetime.utcnow() - timedelta(minutes=31),
        job_status=JOB_STATUS_IN_PROGRESS,
    )
    job_2 = create_job(
        template=sample_template,
        notification_count=3,
        created_at=datetime.utcnow() - timedelta(minutes=31),
        processing_started=datetime.utcnow() - timedelta(minutes=29),
        job_status=JOB_STATUS_IN_PROGRESS,
    )
    check_job_status()

    # job 2 not in celery task
    mock_celery.assert_called_once_with([[str(job.id)]], queue=QueueNames.JOBS)
    assert job.job_status == JOB_STATUS_ERROR
    assert job_2.job_status == JOB_STATUS_IN_PROGRESS


def test_replay_created_notifications(sample_service, mock_celery_task):
    email_delivery_queue = mock_celery_task(deliver_email)
    sms_delivery_queue = mock_celery_task(deliver_sms)

    sms_template = create_template(service=sample_service, template_type="sms")
    email_template = create_template(service=sample_service, template_type="email")
    older_than = (60 * 60) + (60 * 15)  # 1 hour 15 minutes
    # notifications expected to be resent
    old_sms = create_notification(
        template=sms_template, created_at=datetime.utcnow() - timedelta(seconds=older_than), status="created"
    )
    old_email = create_notification(
        template=email_template, created_at=datetime.utcnow() - timedelta(seconds=older_than), status="created"
    )
    # notifications that are not to be resent
    create_notification(
        template=sms_template, created_at=datetime.utcnow() - timedelta(seconds=older_than), status="sending"
    )
    create_notification(
        template=email_template, created_at=datetime.utcnow() - timedelta(seconds=older_than), status="delivered"
    )
    create_notification(template=sms_template, created_at=datetime.utcnow(), status="created")
    create_notification(template=email_template, created_at=datetime.utcnow(), status="created")

    replay_created_notifications()
    email_delivery_queue.assert_called_once_with([str(old_email.id)], queue="send-email-tasks")
    sms_delivery_queue.assert_called_once_with([str(old_sms.id)], queue="send-sms-tasks")


def test_replay_created_notifications_get_pdf_for_templated_letter_tasks_for_letters_not_ready_to_send(
    sample_letter_template, mock_celery_task
):
    mock_task = mock_celery_task(get_pdf_for_templated_letter)
    create_notification(
        template=sample_letter_template, billable_units=0, created_at=datetime.utcnow() - timedelta(hours=4)
    )

    create_notification(
        template=sample_letter_template, billable_units=0, created_at=datetime.utcnow() - timedelta(minutes=20)
    )
    notification_1 = create_notification(
        template=sample_letter_template, billable_units=0, created_at=datetime.utcnow() - timedelta(hours=1, minutes=20)
    )
    notification_2 = create_notification(
        template=sample_letter_template, billable_units=0, created_at=datetime.utcnow() - timedelta(hours=5)
    )

    replay_created_notifications()

    calls = [
        call([str(notification_1.id)], queue=QueueNames.CREATE_LETTERS_PDF),
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
        job_status=JOB_STATUS_FINISHED,
    )
    create_job(
        template=sample_template,
        notification_count=3,
        created_at=datetime.utcnow() - timedelta(minutes=31),
        processing_started=datetime.utcnow() - timedelta(minutes=31),
        job_status=JOB_STATUS_FINISHED,
    )

    check_job_status()


@freeze_time("2019-05-30 14:00:00")
def test_check_if_letters_still_pending_virus_check_restarts_scan_for_stuck_letters(mocker, sample_letter_template):
    mock_file_exists = mocker.patch("app.aws.s3.file_exists", return_value=True)
    mock_create_ticket = mocker.spy(NotifySupportTicket, "__init__")
    mock_celery = mocker.patch("app.celery.scheduled_tasks.notify_celery.send_task")

    create_notification(
        template=sample_letter_template,
        status=NOTIFICATION_PENDING_VIRUS_CHECK,
        created_at=datetime.utcnow() - timedelta(minutes=10, seconds=1),
        reference="one",
    )
    create_notification(
        template=sample_letter_template,
        status=NOTIFICATION_PENDING_VIRUS_CHECK,
        created_at=datetime.utcnow() - timedelta(minutes=9, seconds=59),
        reference="still has time to send",
    )
    create_notification(
        template=sample_letter_template,
        status=NOTIFICATION_PENDING_VIRUS_CHECK,
        created_at=datetime.utcnow() - timedelta(minutes=30, seconds=1),
        reference="too old for us to bother with",
    )
    expected_filename = "NOTIFY.ONE.D.2.C.20190530134959.PDF"

    check_if_letters_still_pending_virus_check()

    mock_file_exists.assert_called_once_with("test-letters-scan", expected_filename)

    mock_celery.assert_called_once_with(
        name=TaskNames.SCAN_FILE, kwargs={"filename": expected_filename}, queue=QueueNames.ANTIVIRUS
    )

    assert mock_create_ticket.called is False


@freeze_time("2019-05-30 14:00:00")
def test_check_if_letters_still_pending_virus_check_raises_zendesk_if_files_cant_be_found(
    sample_letter_template, mocker
):
    mock_file_exists = mocker.patch("app.aws.s3.file_exists", return_value=False)
    mock_create_ticket = mocker.spy(NotifySupportTicket, "__init__")
    mock_celery = mocker.patch("app.celery.scheduled_tasks.notify_celery.send_task")
    mock_send_ticket_to_zendesk = mocker.patch(
        "app.celery.scheduled_tasks.zendesk_client.send_ticket_to_zendesk",
        autospec=True,
    )

    create_notification(
        template=sample_letter_template,
        status=NOTIFICATION_PENDING_VIRUS_CHECK,
        created_at=datetime.utcnow() - timedelta(seconds=600),
        reference="ignore as still has time",
    )
    create_notification(
        template=sample_letter_template,
        status=NOTIFICATION_DELIVERED,
        created_at=datetime.utcnow() - timedelta(seconds=1000),
        reference="ignore as status in delivered",
    )
    notification_1 = create_notification(
        template=sample_letter_template,
        status=NOTIFICATION_PENDING_VIRUS_CHECK,
        created_at=datetime.utcnow() - timedelta(seconds=601),
        reference="one",
    )
    notification_2 = create_notification(
        template=sample_letter_template,
        status=NOTIFICATION_PENDING_VIRUS_CHECK,
        created_at=datetime.utcnow() - timedelta(seconds=1000),
        reference="two",
    )

    check_if_letters_still_pending_virus_check()

    assert mock_file_exists.call_count == 2
    mock_file_exists.assert_has_calls(
        [
            call("test-letters-scan", "NOTIFY.ONE.D.2.C.20190530134959.PDF"),
            call("test-letters-scan", "NOTIFY.TWO.D.2.C.20190530134320.PDF"),
        ],
        any_order=True,
    )
    assert mock_celery.called is False

    mock_create_ticket.assert_called_once_with(
        ANY,
        subject="[test] Letters still pending virus check",
        message=ANY,
        ticket_type="task",
        notify_ticket_type=NotifyTicketType.TECHNICAL,
        notify_task_type="notify_task_letters_pending_scan",
    )
    assert "2 precompiled letters have been pending-virus-check" in mock_create_ticket.call_args.kwargs["message"]
    assert f"{(str(notification_1.id), notification_1.reference)}" in mock_create_ticket.call_args.kwargs["message"]
    assert f"{(str(notification_2.id), notification_2.reference)}" in mock_create_ticket.call_args.kwargs["message"]
    mock_send_ticket_to_zendesk.assert_called_once()


@freeze_time("2019-05-30 14:00:00")
def test_check_if_letters_still_in_created_during_bst(sample_letter_template, caplog, mocker):
    mock_create_ticket = mocker.spy(NotifySupportTicket, "__init__")
    mock_send_ticket_to_zendesk = mocker.patch(
        "app.celery.scheduled_tasks.zendesk_client.send_ticket_to_zendesk",
        autospec=True,
    )

    with caplog.at_level("ERROR"):
        create_notification(template=sample_letter_template, created_at=datetime(2019, 5, 1, 12, 0))
        create_notification(template=sample_letter_template, created_at=datetime(2019, 5, 29, 16, 29))
        create_notification(template=sample_letter_template, created_at=datetime(2019, 5, 29, 16, 30))
        create_notification(template=sample_letter_template, created_at=datetime(2019, 5, 29, 17, 29))
        create_notification(
            template=sample_letter_template, status="delivered", created_at=datetime(2019, 5, 28, 10, 0)
        )
        create_notification(template=sample_letter_template, created_at=datetime(2019, 5, 30, 10, 0))

        check_if_letters_still_in_created()

    assert "2 letter notifications created before 17:30 yesterday still have 'created' status" in caplog.messages
    mock_create_ticket.assert_called_with(
        ANY,
        message=(
            "2 letters were created before 17.30 yesterday and still have 'created' status. "
            "Follow runbook to resolve: "
            "https://github.com/alphagov/notifications-manuals/wiki/Support-Runbook#deal-with-letters-still-in-created."
        ),
        subject="[test] Letters still in 'created' status",
        ticket_type="task",
        notify_ticket_type=NotifyTicketType.TECHNICAL,
        notify_task_type="notify_task_letters_created_status",
    )
    mock_send_ticket_to_zendesk.assert_called_once()


@freeze_time("2019-01-30 14:00:00")
def test_check_if_letters_still_in_created_during_utc(sample_letter_template, caplog, mocker):
    mock_create_ticket = mocker.spy(NotifySupportTicket, "__init__")
    mock_send_ticket_to_zendesk = mocker.patch(
        "app.celery.scheduled_tasks.zendesk_client.send_ticket_to_zendesk",
        autospec=True,
    )

    with caplog.at_level("ERROR"):
        create_notification(template=sample_letter_template, created_at=datetime(2018, 12, 1, 12, 0))
        create_notification(template=sample_letter_template, created_at=datetime(2019, 1, 29, 17, 29))
        create_notification(template=sample_letter_template, created_at=datetime(2019, 1, 29, 17, 30))
        create_notification(template=sample_letter_template, created_at=datetime(2019, 1, 29, 18, 29))
        create_notification(
            template=sample_letter_template, status="delivered", created_at=datetime(2019, 1, 29, 10, 0)
        )
        create_notification(template=sample_letter_template, created_at=datetime(2019, 1, 30, 10, 0))

        check_if_letters_still_in_created()

    assert "2 letter notifications created before 17:30 yesterday still have 'created' status" in caplog.messages
    mock_create_ticket.assert_called_once_with(
        ANY,
        message=(
            "2 letters were created before 17.30 yesterday and still have 'created' status. "
            "Follow runbook to resolve: "
            "https://github.com/alphagov/notifications-manuals/wiki/Support-Runbook#deal-with-letters-still-in-created."
        ),
        subject="[test] Letters still in 'created' status",
        ticket_type="task",
        notify_ticket_type=NotifyTicketType.TECHNICAL,
        notify_task_type="notify_task_letters_created_status",
    )
    mock_send_ticket_to_zendesk.assert_called_once()


@pytest.mark.parametrize(
    "offset",
    (
        timedelta(days=1),
        pytest.param(timedelta(hours=23, minutes=59), marks=pytest.mark.xfail),
        pytest.param(timedelta(minutes=20), marks=pytest.mark.xfail),
        timedelta(minutes=19),
    ),
)
def test_check_for_missing_rows_in_completed_jobs_ignores_old_and_new_jobs(
    mocker,
    sample_email_template,
    offset,
):
    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=(load_example_csv("multiple_email"), {"sender_id": None}),
    )
    mocker.patch("app.signing.encode", return_value="something_encoded")
    get_id_task_args_kwargs_for_job_row = mocker.patch("app.celery.scheduled_tasks.get_id_task_args_kwargs_for_job_row")
    process_job_row = mocker.patch("app.celery.scheduled_tasks.process_job_row")

    job = create_job(
        template=sample_email_template,
        notification_count=5,
        job_status=JOB_STATUS_FINISHED,
        processing_finished=datetime.utcnow() - offset,
    )
    for i in range(4):
        create_notification(job=job, job_row_number=i)

    check_for_missing_rows_in_completed_jobs()

    assert get_id_task_args_kwargs_for_job_row.called is False
    assert process_job_row.called is False


def test_check_for_missing_rows_in_completed_jobs(mocker, sample_email_template, mock_celery_task):
    job = create_job(
        template=sample_email_template,
        notification_count=5,
        job_status=JOB_STATUS_FINISHED,
        processing_finished=datetime.utcnow() - timedelta(minutes=20),
    )
    for i in range(4):
        create_notification(job=job, job_row_number=i)

    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=(load_example_csv("multiple_email"), {"sender_id": None}),
    )
    mock_encode = mocker.patch("app.signing.encode", return_value="something_encoded")
    mocker.patch("app.celery.tasks.create_uuid", return_value="some-uuid")
    mock_save_email = mock_celery_task(save_email)

    check_for_missing_rows_in_completed_jobs()

    assert mock_encode.mock_calls == [
        mock.call(
            {
                "template": str(job.template_id),
                "template_version": job.template_version,
                "job": str(job.id),
                "to": "test5@test.com",
                "row_number": 4,
                "personalisation": {"emailaddress": "test5@test.com"},
                "client_reference": None,
            }
        )
    ]
    assert mock_save_email.mock_calls == [
        mock.call((str(job.service_id), "some-uuid", "something_encoded"), {}, queue="database-tasks")
    ]


def test_check_for_missing_rows_in_completed_jobs_uses_sender_id(
    mocker, sample_email_template, fake_uuid, mock_celery_task
):
    job = create_job(
        template=sample_email_template,
        notification_count=5,
        job_status=JOB_STATUS_FINISHED,
        processing_finished=datetime.utcnow() - timedelta(minutes=20),
    )
    for i in range(4):
        create_notification(job=job, job_row_number=i)

    mocker.patch(
        "app.celery.tasks.s3.get_job_and_metadata_from_s3",
        return_value=(load_example_csv("multiple_email"), {"sender_id": fake_uuid}),
    )
    mock_encode = mocker.patch("app.signing.encode", return_value="something_encoded")
    mocker.patch("app.celery.tasks.create_uuid", return_value="some-uuid")
    mock_save_email = mock_celery_task(save_email)

    check_for_missing_rows_in_completed_jobs()

    assert mock_encode.mock_calls == [
        mock.call(
            {
                "template": str(job.template_id),
                "template_version": job.template_version,
                "job": str(job.id),
                "to": "test5@test.com",
                "row_number": 4,
                "personalisation": {"emailaddress": "test5@test.com"},
                "client_reference": None,
            }
        )
    ]
    assert mock_save_email.mock_calls == [
        mock.call(
            (str(job.service_id), "some-uuid", "something_encoded"), {"sender_id": fake_uuid}, queue="database-tasks"
        )
    ]


def test_update_status_of_fully_processed_jobs(mocker, sample_email_template, mock_celery_task):
    job = create_job(
        template=sample_email_template,
        notification_count=5,
        job_status=JOB_STATUS_FINISHED,
        processing_finished=datetime.utcnow() - timedelta(minutes=3),
    )
    for i in range(5):
        create_notification(job=job, job_row_number=i)

    update_status_of_fully_processed_jobs()

    assert job.job_status == JOB_STATUS_FINISHED_ALL_NOTIFICATIONS_CREATED


MockServicesSendingToTVNumbers = namedtuple(
    "MockServicesSendingToTVNumbers",
    [
        "service_id",
        "notification_count",
    ],
)
MockServicesWithHighFailureRate = namedtuple(
    "MockServicesWithHighFailureRate",
    [
        "service_id",
        "permanent_failure_rate",
    ],
)


@pytest.mark.parametrize(
    "failure_rates, sms_to_tv_numbers, expected_logs, expected_message",
    [
        [
            [MockServicesWithHighFailureRate("123", 0.3), MockServicesWithHighFailureRate("456", 0.7)],
            [],
            [
                "Service 123 has had a high permanent-failure rate (0.3) for text messages in the last 24 hours",
                "Service 456 has had a high permanent-failure rate (0.7) for text messages in the last 24 hours",
            ],
            "2 service(s) have had high permanent-failure rates for sms messages in last 24 hours:\n"
            f"service: {Config.ADMIN_BASE_URL}/services/123 failure rate: 0.3,\n"
            f"service: {Config.ADMIN_BASE_URL}/services/456 failure rate: 0.7,\n",
        ],
        [
            [],
            [MockServicesSendingToTVNumbers("123", 567)],
            ["Service 123 has sent 567 text messages to tv numbers in the last 24 hours"],
            "1 service(s) have sent over 500 sms messages to tv numbers in last 24 hours:\n"
            f"service: {Config.ADMIN_BASE_URL}/services/123 count of sms to tv numbers: 567,\n",
        ],
        [
            [MockServicesWithHighFailureRate("123", 0.3)],
            [MockServicesSendingToTVNumbers("456", 567)],
            [
                "Service 123 has had a high permanent-failure rate (0.3) for text messages in the last 24 hours",
                "Service 456 has sent 567 text messages to tv numbers in the last 24 hours",
            ],
            "1 service(s) have had high permanent-failure rates for sms messages in last 24 hours:\n"
            f"service: {Config.ADMIN_BASE_URL}/services/123 failure rate: 0.3,\n"
            "1 service(s) have sent over 500 sms messages to tv numbers in last 24 hours:\n"
            f"service: {Config.ADMIN_BASE_URL}/services/456 count of sms to tv numbers: 567,\n",
        ],
    ],
)
def test_check_for_services_with_high_failure_rates_or_sending_to_tv_numbers(
    notify_db_session, failure_rates, sms_to_tv_numbers, expected_logs, expected_message, caplog, mocker
):
    mock_create_ticket = mocker.spy(NotifySupportTicket, "__init__")
    mock_send_ticket_to_zendesk = mocker.patch(
        "app.celery.scheduled_tasks.zendesk_client.send_ticket_to_zendesk",
        autospec=True,
    )
    mock_failure_rates = mocker.patch(
        "app.celery.scheduled_tasks.dao_find_services_with_high_failure_rates", return_value=failure_rates
    )
    mock_sms_to_tv_numbers = mocker.patch(
        "app.celery.scheduled_tasks.dao_find_services_sending_to_tv_numbers", return_value=sms_to_tv_numbers
    )

    zendesk_actions = "\nYou can find instructions for this ticket in our manual:\nhttps://github.com/alphagov/notifications-manuals/wiki/Support-Runbook#deal-with-services-with-high-failure-rates-or-sending-sms-to-tv-numbers"

    with caplog.at_level("WARNING"):
        check_for_services_with_high_failure_rates_or_sending_to_tv_numbers()

    assert mock_failure_rates.called
    assert mock_sms_to_tv_numbers.called
    assert set(expected_logs) == set(caplog.messages)
    mock_create_ticket.assert_called_with(
        ANY,
        message=expected_message + zendesk_actions,
        subject="[test] High failure rates for sms spotted for services",
        ticket_type="task",
        notify_ticket_type=NotifyTicketType.TECHNICAL,
        notify_task_type="notify_task_high_failure",
    )
    mock_send_ticket_to_zendesk.assert_called_once()


def test_delete_old_records_from_events_table(notify_db_session):
    old_datetime, recent_datetime = datetime.utcnow() - timedelta(weeks=78), datetime.utcnow() - timedelta(weeks=50)
    old_event = Event(event_type="test_event", created_at=old_datetime, data={})
    recent_event = Event(event_type="test_event", created_at=recent_datetime, data={})

    notify_db_session.add(old_event)
    notify_db_session.add(recent_event)
    notify_db_session.commit()

    delete_old_records_from_events_table()

    events = Event.query.filter(Event.event_type == "test_event").all()
    assert len(events) == 1
    assert events[0].created_at == recent_datetime


@freeze_time("2022-11-01 00:30:00", tick=True)
def test_zendesk_new_email_branding_report(notify_db_session, notify_user, hostnames, mocker):
    org_1 = create_organisation(organisation_id=uuid.UUID("113d51e7-f204-44d0-99c6-020f3542a527"), name="org-1")
    org_2 = create_organisation(organisation_id=uuid.UUID("d6bc2309-9f79-4779-b864-46c2892db90e"), name="org-2")
    email_brand_1 = create_email_branding(
        id=uuid.UUID("bc5b45e0-af3c-4e3d-a14c-253a56b77480"), name="brand-1", created_by=notify_user.id
    )
    email_brand_2 = create_email_branding(
        id=uuid.UUID("c9c265b3-14ec-42f1-8ae9-4749ffc6f5b0"), name="brand-2", created_by=notify_user.id
    )
    create_email_branding(
        id=uuid.UUID("1b7deb1f-ff1f-4d00-a7a7-05b0b57a185e"), name="brand-3", created_by=notify_user.id
    )
    org_1.email_branding_pool = [email_brand_1, email_brand_2]
    org_2.email_branding_pool = [email_brand_2]
    org_2.email_branding = email_brand_1
    notify_db_session.commit()

    mock_send_ticket = mocker.patch("app.celery.scheduled_tasks.zendesk_client.send_ticket_to_zendesk")

    zendesk_new_email_branding_report()

    assert mock_send_ticket.call_count == 1

    ticket = mock_send_ticket.call_args_list[0][0][0]

    assert ticket.request_data == {
        "ticket": {
            "subject": "Review new email brandings",
            "comment": {
                "html_body": mocker.ANY,
                "public": True,
            },
            "group_id": 360000036529,
            "organization_id": 21891972,
            "ticket_form_id": 14226867890588,
            "priority": "normal",
            "tags": ["govuk_notify_support"],
            "type": "task",
            "custom_fields": [
                {"id": "14229641690396", "value": "notify_task_branding_review"},
                {"id": "360022943959", "value": None},
                {"id": "360022943979", "value": None},
                {"id": "1900000745014", "value": None},
                {"id": "15925693889308", "value": None},
                {"id": "1900000744994", "value": "notify_ticket_type_non_technical"},
            ],
        }
    }

    for expected_html_fragment in (
        "<h2>New email branding to review</h2>\n<p>Uploaded since Monday 31 October 2022:</p>",
        (
            "<p>"
            f'<a href="{hostnames.admin}/organisations/'
            '113d51e7-f204-44d0-99c6-020f3542a527/settings/email-branding">org-1</a> (no default):'
            "</p>"
            "<ul>"
            "<li>"
            f'<a href="{hostnames.admin}/email-branding/bc5b45e0-af3c-4e3d-a14c-253a56b77480">brand-1</a>'
            "</li>"
            "<li>"
            f'<a href="{hostnames.admin}/email-branding/c9c265b3-14ec-42f1-8ae9-4749ffc6f5b0">brand-2</a>'
            "</li>"
            "</ul>"
            "<hr>"
            "<p>"
            f'<a href="{hostnames.admin}/organisations/'
            'd6bc2309-9f79-4779-b864-46c2892db90e/settings/email-branding">org-2</a>:'
            "</p>"
            "<ul>"
            "<li>"
            f'<a href="{hostnames.admin}/email-branding/c9c265b3-14ec-42f1-8ae9-4749ffc6f5b0">brand-2</a>'
            "</li>"
            "</ul>"
        ),
        (
            "<p>These new brands are not associated with any organisation and do not need reviewing:</p>"
            "<ul>"
            "<li>"
            f'<a href="{hostnames.admin}/email-branding/1b7deb1f-ff1f-4d00-a7a7-05b0b57a185e">brand-3</a>'
            "</li>"
            "</ul>"
        ),
    ):
        assert expected_html_fragment in ticket.request_data["ticket"]["comment"]["html_body"]


@freeze_time("2022-11-01 00:30:00")
def test_zendesk_new_email_branding_report_for_unassigned_branding_only(
    notify_db_session, notify_user, hostnames, mocker
):
    create_organisation(organisation_id=uuid.UUID("113d51e7-f204-44d0-99c6-020f3542a527"), name="org-1")
    create_organisation(organisation_id=uuid.UUID("d6bc2309-9f79-4779-b864-46c2892db90e"), name="org-2")
    create_email_branding(
        id=uuid.UUID("bc5b45e0-af3c-4e3d-a14c-253a56b77480"), name="brand-1", created_by=notify_user.id
    )
    create_email_branding(
        id=uuid.UUID("c9c265b3-14ec-42f1-8ae9-4749ffc6f5b0"), name="brand-2", created_by=notify_user.id
    )
    create_email_branding(
        id=uuid.UUID("1b7deb1f-ff1f-4d00-a7a7-05b0b57a185e"), name="brand-3", created_by=notify_user.id
    )
    notify_db_session.commit()

    mock_send_ticket = mocker.patch("app.celery.scheduled_tasks.zendesk_client.send_ticket_to_zendesk")

    zendesk_new_email_branding_report()

    assert mock_send_ticket.call_args_list[0][0][0].request_data["ticket"]["comment"]["html_body"] == (
        "<p>These new brands are not associated with any organisation and do not need reviewing:</p>"
        "<ul>"
        "<li>"
        f'<a href="{hostnames.admin}/email-branding/bc5b45e0-af3c-4e3d-a14c-253a56b77480">brand-1</a>'
        "</li><li>"
        f'<a href="{hostnames.admin}/email-branding/c9c265b3-14ec-42f1-8ae9-4749ffc6f5b0">brand-2</a>'
        "</li><li>"
        f'<a href="{hostnames.admin}/email-branding/1b7deb1f-ff1f-4d00-a7a7-05b0b57a185e">brand-3</a>'
        "</li>"
        "</ul>"
    )


@pytest.mark.parametrize(
    "task_run_time, earliest_searched_timestamp, expected_last_day_string",
    (
        ("2023-03-24 00:30:00", "2023-03-23 00:00:00", "Thursday 23 March 2023"),
        ("2023-03-25 00:30:00", "2023-03-24 00:00:00", "Friday 24 March 2023"),
        ("2023-03-26 00:30:00", "2023-03-24 00:00:00", "Friday 24 March 2023"),  # Sunday morning, DST changeover
        ("2023-03-26 23:30:00", "2023-03-24 00:00:00", "Friday 24 March 2023"),  # Monday morning early AM
        ("2023-03-27 23:30:00", "2023-03-26 23:00:00", "Monday 27 March 2023"),
        ("2023-03-28 23:30:00", "2023-03-27 23:00:00", "Tuesday 28 March 2023"),
        ("2023-03-29 23:30:00", "2023-03-28 23:00:00", "Wednesday 29 March 2023"),
    ),
)
def test_zendesk_new_email_branding_report_calculates_last_weekday_correctly(
    notify_db_session, task_run_time, earliest_searched_timestamp, expected_last_day_string, notify_user, mocker
):
    org_1 = create_organisation()

    new_brand_ts = dateutil.parser.parse(earliest_searched_timestamp)
    old_brand_ts = new_brand_ts - timedelta(seconds=1)

    old_brand = create_email_branding(
        name="old brand",
        created_by=notify_user.id,
        created_at=old_brand_ts,
    )
    new_brand = create_email_branding(
        name="new brand",
        created_by=notify_user.id,
        created_at=new_brand_ts,
    )

    org_1.email_branding_pool = [old_brand, new_brand]
    notify_db_session.commit()

    mocker.patch("app.celery.scheduled_tasks.NotifySupportTicket", wraps=NotifySupportTicket)
    mock_send_ticket = mocker.patch("app.celery.scheduled_tasks.zendesk_client.send_ticket_to_zendesk")

    with freeze_time(task_run_time):
        zendesk_new_email_branding_report()

    message = mock_send_ticket.call_args_list[0][0][0].message
    assert expected_last_day_string in message
    assert "old brand" not in message
    assert "new brand" in message


def test_zendesk_new_email_branding_report_does_not_create_ticket_if_no_new_brands(notify_db_session, mocker):
    mock_send_ticket = mocker.patch("app.celery.scheduled_tasks.zendesk_client.send_ticket_to_zendesk")
    zendesk_new_email_branding_report()
    assert mock_send_ticket.call_args_list == []


@freeze_time("2022-11-01 00:30:00")
def test_zendesk_new_email_branding_report_does_not_report_on_brands_created_by_platform_admin(
    notify_db_session, mocker
):
    plain_user = create_user(email="plain@notify.works", platform_admin=False)
    platform_user = create_user(email="platform@notify.works", platform_admin=True)
    brand_1 = create_email_branding(name="brand-1", created_by=plain_user.id)
    brand_2 = create_email_branding(name="brand-2", created_by=plain_user.id)
    brand_3 = create_email_branding(name="brand-3", created_by=platform_user.id)
    notify_db_session.commit()

    mock_send_ticket = mocker.patch("app.celery.scheduled_tasks.zendesk_client.send_ticket_to_zendesk")

    zendesk_new_email_branding_report()

    # 1 brand was made by a platform admin - 2 were not. We should report on/link to those 2 brands.
    ticket_html = mock_send_ticket.call_args_list[0][0][0].request_data["ticket"]["comment"]["html_body"]
    assert ticket_html.count("<li><a href") == 2
    assert str(brand_1.id) in ticket_html
    assert str(brand_2.id) in ticket_html
    assert str(brand_3.id) not in ticket_html


def test_check_for_low_available_inbound_sms_numbers_logs_zendesk_ticket_if_too_few_numbers(
    notify_api, notify_db_session, mocker
):
    mocker.patch(
        "app.celery.scheduled_tasks.dao_get_available_inbound_numbers",
        return_value=[InboundNumber() for _ in range(5)],
    )
    mock_ticket = mocker.patch("app.celery.scheduled_tasks.NotifySupportTicket")
    mock_send_ticket = mocker.patch("app.celery.scheduled_tasks.zendesk_client.send_ticket_to_zendesk")

    with set_config(notify_api, "LOW_INBOUND_SMS_NUMBER_THRESHOLD", 10):
        check_for_low_available_inbound_sms_numbers()

    # Make sure we've built a NotifySupportTicket with the expected params, and passed that ticket to the zendesk client
    assert mock_ticket.call_args_list == [
        mocker.call(
            subject="Request more inbound SMS numbers",
            message=(
                "There are only 5 inbound SMS numbers currently available for services.\n\n"
                "Request more from our provider (MMG) and load them into the database.\n\n"
                "Follow the guidance here: "
                "https://github.com/alphagov/notifications-manuals/wiki/Support-Runbook#add-new-inbound-sms-numbers"
            ),
            ticket_type=mock_ticket.TYPE_TASK,
            notify_ticket_type=NotifyTicketType.TECHNICAL,
            notify_task_type="notify_task_request_inbound_SMS",
        )
    ]
    assert mock_send_ticket.call_args_list == [mocker.call(mock_ticket.return_value)]


def test_check_for_low_available_inbound_sms_numbers_does_not_proceed_if_enough_numbers(
    notify_api, notify_db_session, mocker
):
    mocker.patch(
        "app.celery.scheduled_tasks.dao_get_available_inbound_numbers",
        return_value=[InboundNumber() for _ in range(11)],
    )
    mock_send_ticket = mocker.patch("app.celery.scheduled_tasks.zendesk_client.send_ticket_to_zendesk")

    with set_config(notify_api, "LOW_INBOUND_SMS_NUMBER_THRESHOLD", 10):
        check_for_low_available_inbound_sms_numbers()

    assert mock_send_ticket.call_args_list == []


@freeze_time("2024-08-14T10:00:00")
def test_weekly_user_research_email(notify_api, user_research_email_for_new_users_template, notify_db_session, mocker):
    mock_send_email = mocker.patch("app.celery.scheduled_tasks.send_notification_to_queue")

    create_user(email="user1@gov.uk", take_part_in_research=True, created_at=datetime(2024, 7, 29, 12, 0))
    create_user(email="user2@gov.uk", take_part_in_research=True, created_at=datetime(2024, 8, 1, 14))
    create_user(email="user3@gov.uk", take_part_in_research=True, created_at=datetime(2024, 8, 4, 23, 59))

    # user does not receive email
    create_user(email="user4@gov.uk", take_part_in_research=True, created_at=datetime(2024, 8, 5))

    with set_config(notify_api, "WEEKLY_USER_RESEARCH_EMAIL_ENABLED", True):
        weekly_user_research_email()

    assert mock_send_email.call_args_list == [
        call(ANY, queue="notify-internal-tasks"),
        call(ANY, queue="notify-internal-tasks"),
        call(ANY, queue="notify-internal-tasks"),
    ]

    notifications = Notification.query.all()
    assert {email.to for email in notifications} == {"user1@gov.uk", "user2@gov.uk", "user3@gov.uk"}


@freeze_time("2024-08-14T10:00:00")
def test_weekly_user_research_email_skips_environments_with_setting_disabled(
    notify_api, user_research_email_for_new_users_template, notify_db_session, caplog, mocker
):
    mock_send_email = mocker.patch("app.celery.scheduled_tasks.send_notification_to_queue")

    create_user(email="user1@gov.uk", take_part_in_research=True, created_at=datetime(2024, 7, 29, 12, 0))
    create_user(email="user2@gov.uk", take_part_in_research=True, created_at=datetime(2024, 8, 1, 14))
    create_user(email="user3@gov.uk", take_part_in_research=True, created_at=datetime(2024, 8, 4, 23, 59))
    create_user(email="user4@gov.uk", take_part_in_research=True, created_at=datetime(2024, 8, 5))

    with set_config(notify_api, "WEEKLY_USER_RESEARCH_EMAIL_ENABLED", False):
        weekly_user_research_email()

    assert (
        "Not running weekly-user-research-email - configured not to send weekly user research email" in caplog.messages
    )
    assert not mock_send_email.called


class TestChangeDvlaPasswordTask:
    def test_calls_dvla_succesfully(self, mocker, notify_api):
        mock_change_password = mocker.patch("app.dvla_client.change_password")

        change_dvla_password()

        mock_change_password.assert_called_once_with()

    def test_silently_quits_if_lock_is_held(self, mocker, notify_api):
        mocker.patch("app.dvla_client.change_password", side_effect=LockError)

        # does not raise any exceptions
        change_dvla_password()

    def test_retries_if_dvla_throws_retryable_exception(self, mocker, notify_api):
        mocker.patch("app.dvla_client.change_password", side_effect=DvlaThrottlingException)

        with pytest.raises(Retry):
            change_dvla_password()

    def test_reraises_if_dvla_raises_non_retryable_exception(self, mocker, notify_api):
        mocker.patch("app.dvla_client.change_password", side_effect=DvlaNonRetryableException)

        with pytest.raises(DvlaNonRetryableException):
            change_dvla_password()


class TestChangeDvlaApiKeyTask:
    def test_calls_dvla_succesfully(self, mocker, notify_api):
        mock_change_api_key = mocker.patch("app.dvla_client.change_api_key")

        change_dvla_api_key()

        mock_change_api_key.assert_called_once_with()

    def test_silently_quits_if_lock_is_held(self, mocker):
        mocker.patch("app.dvla_client.change_api_key", side_effect=LockError)

        # does not raise any exceptions
        change_dvla_api_key()

    def test_retries_if_dvla_throws_retryable_exception(self, mocker):
        mocker.patch("app.dvla_client.change_api_key", side_effect=DvlaThrottlingException)

        with pytest.raises(Retry):
            change_dvla_api_key()

    def test_reraises_if_dvla_raises_non_retryable_exception(self, mocker):
        mocker.patch("app.dvla_client.change_api_key", side_effect=DvlaNonRetryableException)

        with pytest.raises(DvlaNonRetryableException):
            change_dvla_api_key()


class TestWeeklyDWPReport:
    @pytest.fixture(scope="function")
    def mock_zendesk_update_ticket(self, notify_api, mocker):
        yield mocker.patch("app.celery.scheduled_tasks.zendesk_client.update_ticket")

    @pytest.fixture(scope="function")
    def mock_env_with_zendesk_alerts_enabled(self, notify_api, mocker):
        with set_config(notify_api, "SEND_ZENDESK_ALERTS_ENABLED", True):
            yield notify_api

    @pytest.mark.parametrize(
        "environment, send_zendesk_alerts_enabled, should_run",
        (
            ("example-env-1", False, False),
            ("example-env-2", True, True),
        ),
    )
    def test_skips_environments_with_zendesk_alerts_disabled(
        self,
        notify_api,
        notify_db_session,
        mock_zendesk_update_ticket,
        caplog,
        environment,
        send_zendesk_alerts_enabled,
        should_run,
    ):
        with set_config_values(
            notify_api, {"NOTIFY_ENVIRONMENT": environment, "SEND_ZENDESK_ALERTS_ENABLED": send_zendesk_alerts_enabled}
        ):
            weekly_dwp_report()

        assert (
            "Not running weekly-dwp-report - configured not to send zendesk alerts" in caplog.messages
        ) != should_run

        # 'Successful' runs for this test still don't get to the zendesk_update_ticket call because of other checks.
        assert mock_zendesk_update_ticket.call_args_list == []

    @pytest.mark.parametrize(
        "report_config",
        [
            {"weekly-dwp-report": {}},
            {"weekly-dwp-report": {"query": {}, "ticket_id": 123456}},
            {"weekly-dwp-report": {"query": {"report.csv": "select 1"}, "ticket_id": None}},
            {"weekly-dwp-report": {"query": {"report.csv": "select 1"}, "ticket_id": 0}},
        ],
    )
    def test_requires_zendesk_reporting_config(
        self, mock_env_with_zendesk_alerts_enabled, notify_db_session, mock_zendesk_update_ticket, caplog, report_config
    ):
        with set_config(mock_env_with_zendesk_alerts_enabled, "ZENDESK_REPORTING", report_config):
            weekly_dwp_report()

        assert "Skipping DWP report run - invalid configuration." in caplog.messages
        assert mock_zendesk_update_ticket.call_args_list == []

    @freeze_time("2022-01-01T09:00:00")
    def test_successful_run(
        self, mock_env_with_zendesk_alerts_enabled, notify_db_session, mock_zendesk_update_ticket, mocker
    ):
        with set_config(
            mock_env_with_zendesk_alerts_enabled,
            "ZENDESK_REPORTING",
            {
                "weekly-dwp-report": {
                    "query": {
                        "some-data.csv": "select 1 as result, 'something else' as text, 'quote,text' as comma",
                    },
                    "ticket_id": 123456,
                }
            },
        ):
            weekly_dwp_report()

        assert mock_zendesk_update_ticket.call_args_list == [
            mocker.call(
                123456,
                status=NotifySupportTicketStatus.PENDING,
                comment=NotifySupportTicketComment(
                    body="Please find attached your weekly report.",
                    attachments=[
                        NotifySupportTicketAttachment(
                            filename="some-data.csv", filedata=mocker.ANY, content_type="text/csv"
                        ),
                    ],
                    public=True,
                ),
                due_at=datetime(2022, 1, 8, 12, 10, 0),
            )
        ]
        csv_file = mock_zendesk_update_ticket.call_args_list[0][1]["comment"].attachments[0].filedata
        assert csv_file.read() == 'result,text,comma\r\n1,something else,"quote,text"\r\n'


def test_populate_annual_billing_missing_services_only(mocker, sample_service):
    mock_set = mocker.patch(
        "app.celery.scheduled_tasks.set_default_free_allowance_for_service",
        side_effect=set_default_free_allowance_for_service,
    )

    # No AnnualBilling, should get created
    populate_annual_billing(2023, True)
    assert mock_set.call_args_list == [mocker.call(sample_service, 2023)]

    # AnnualBilling exists and we are only processing missing services, nothing should happen
    mock_set.reset_mock()
    populate_annual_billing(2023, True)
    assert mock_set.call_args_list == []

    # AnnualBilling exists but we are re-processing all services, should get re-evaluated
    mock_set.reset_mock()
    populate_annual_billing(2023, False)
    assert mock_set.call_args_list == [mocker.call(sample_service, 2023)]


@freeze_time("2022-03-01")
def test_run_populate_annual_billing_uses_correct_year(mocker, notify_api):
    populate_annual_billing = mocker.patch("app.celery.scheduled_tasks.populate_annual_billing")

    run_populate_annual_billing()

    populate_annual_billing.assert_called_once_with(year=2021, missing_services_only=True)
