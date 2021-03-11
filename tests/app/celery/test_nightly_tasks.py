from datetime import date, datetime, timedelta
from unittest.mock import PropertyMock, call, patch

import pytest
import pytz
from flask import current_app
from freezegun import freeze_time
from notifications_utils.clients.zendesk.zendesk_client import ZendeskClient

from app.celery import nightly_tasks
from app.celery.nightly_tasks import (
    delete_email_notifications_older_than_retention,
    delete_inbound_sms,
    delete_letter_notifications_older_than_retention,
    delete_sms_notifications_older_than_retention,
    get_letter_notifications_still_sending_when_they_shouldnt_be,
    letter_raise_alert_if_no_ack_file_for_zip,
    raise_alert_if_letter_notifications_still_sending,
    remove_letter_csv_files,
    remove_sms_email_csv_files,
    s3,
    save_daily_notification_processing_time,
    send_daily_performance_platform_stats,
    send_total_sent_notifications_to_performance_platform,
    timeout_notifications,
)
from app.celery.service_callback_tasks import (
    create_delivery_status_callback_data,
)
from app.clients.performance_platform.performance_platform_client import (
    PerformancePlatformClient,
)
from app.config import QueueNames
from app.exceptions import NotificationTechnicalFailureException
from app.models import EMAIL_TYPE, LETTER_TYPE, SMS_TYPE, FactProcessingTime
from tests.app.db import (
    create_ft_notification_status,
    create_job,
    create_notification,
    create_service,
    create_service_callback_api,
    create_service_data_retention,
    create_template,
)


def mock_s3_get_list_match(bucket_name, subfolder='', suffix='', last_modified=None):
    if subfolder == '2018-01-11/zips_sent':
        return ['NOTIFY.2018-01-11175007.ZIP.TXT', 'NOTIFY.2018-01-11175008.ZIP.TXT']
    if subfolder == 'root/dispatch':
        return ['root/dispatch/NOTIFY.2018-01-11175007.ACK.txt', 'root/dispatch/NOTIFY.2018-01-11175008.ACK.txt']


def mock_s3_get_list_diff(bucket_name, subfolder='', suffix='', last_modified=None):
    if subfolder == '2018-01-11/zips_sent':
        return ['NOTIFY.2018-01-11175007p.ZIP.TXT', 'NOTIFY.2018-01-11175008.ZIP.TXT',
                'NOTIFY.2018-01-11175009.ZIP.TXT', 'NOTIFY.2018-01-11175010.ZIP.TXT']
    if subfolder == 'root/dispatch':
        return ['root/disoatch/NOTIFY.2018-01-11175007p.ACK.TXT', 'root/disoatch/NOTIFY.2018-01-11175008.ACK.TXT']


@freeze_time('2016-10-18T10:00:00')
def test_will_remove_csv_files_for_jobs_older_than_seven_days(
        notify_db, notify_db_session, mocker, sample_template
):
    """
    Jobs older than seven days are deleted, but only two day's worth (two-day window)
    """
    mocker.patch('app.celery.nightly_tasks.s3.remove_job_from_s3')

    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    just_under_seven_days = seven_days_ago + timedelta(seconds=1)
    eight_days_ago = seven_days_ago - timedelta(days=1)
    nine_days_ago = eight_days_ago - timedelta(days=1)
    just_under_nine_days = nine_days_ago + timedelta(seconds=1)
    nine_days_one_second_ago = nine_days_ago - timedelta(seconds=1)

    create_job(sample_template, created_at=nine_days_one_second_ago, archived=True)
    job1_to_delete = create_job(sample_template, created_at=eight_days_ago)
    job2_to_delete = create_job(sample_template, created_at=just_under_nine_days)
    dont_delete_me_1 = create_job(sample_template, created_at=seven_days_ago)
    create_job(sample_template, created_at=just_under_seven_days)

    remove_sms_email_csv_files()

    assert s3.remove_job_from_s3.call_args_list == [
        call(job1_to_delete.service_id, job1_to_delete.id),
        call(job2_to_delete.service_id, job2_to_delete.id),
    ]
    assert job1_to_delete.archived is True
    assert dont_delete_me_1.archived is False


@freeze_time('2016-10-18T10:00:00')
def test_will_remove_csv_files_for_jobs_older_than_retention_period(
    notify_db, notify_db_session, mocker
):
    """
    Jobs older than retention period are deleted, but only two day's worth (two-day window)
    """
    mocker.patch('app.celery.nightly_tasks.s3.remove_job_from_s3')
    service_1 = create_service(service_name='service 1')
    service_2 = create_service(service_name='service 2')
    create_service_data_retention(service=service_1, notification_type=SMS_TYPE, days_of_retention=3)
    create_service_data_retention(service=service_2, notification_type=EMAIL_TYPE, days_of_retention=30)
    sms_template_service_1 = create_template(service=service_1)
    email_template_service_1 = create_template(service=service_1, template_type='email')

    sms_template_service_2 = create_template(service=service_2)
    email_template_service_2 = create_template(service=service_2, template_type='email')

    four_days_ago = datetime.utcnow() - timedelta(days=4)
    eight_days_ago = datetime.utcnow() - timedelta(days=8)
    thirty_one_days_ago = datetime.utcnow() - timedelta(days=31)

    job1_to_delete = create_job(sms_template_service_1, created_at=four_days_ago)
    job2_to_delete = create_job(email_template_service_1, created_at=eight_days_ago)
    create_job(email_template_service_1, created_at=four_days_ago)

    create_job(email_template_service_2, created_at=eight_days_ago)
    job3_to_delete = create_job(email_template_service_2, created_at=thirty_one_days_ago)
    job4_to_delete = create_job(sms_template_service_2, created_at=eight_days_ago)

    remove_sms_email_csv_files()

    s3.remove_job_from_s3.assert_has_calls([
        call(job1_to_delete.service_id, job1_to_delete.id),
        call(job2_to_delete.service_id, job2_to_delete.id),
        call(job3_to_delete.service_id, job3_to_delete.id),
        call(job4_to_delete.service_id, job4_to_delete.id)
    ], any_order=True)


@freeze_time('2017-01-01 10:00:00')
def test_remove_csv_files_filters_by_type(mocker, sample_service):
    mocker.patch('app.celery.nightly_tasks.s3.remove_job_from_s3')
    """
    Jobs older than seven days are deleted, but only two day's worth (two-day window)
    """
    letter_template = create_template(service=sample_service, template_type=LETTER_TYPE)
    sms_template = create_template(service=sample_service, template_type=SMS_TYPE)

    eight_days_ago = datetime.utcnow() - timedelta(days=8)

    job_to_delete = create_job(template=letter_template, created_at=eight_days_ago)
    create_job(template=sms_template, created_at=eight_days_ago)

    remove_letter_csv_files()

    assert s3.remove_job_from_s3.call_args_list == [
        call(job_to_delete.service_id, job_to_delete.id),
    ]


def test_should_call_delete_sms_notifications_more_than_week_in_task(notify_api, mocker):
    mocked = mocker.patch('app.celery.nightly_tasks.delete_notifications_older_than_retention_by_type')
    delete_sms_notifications_older_than_retention()
    mocked.assert_called_once_with('sms')


def test_should_call_delete_email_notifications_more_than_week_in_task(notify_api, mocker):
    mocked_notifications = mocker.patch(
        'app.celery.nightly_tasks.delete_notifications_older_than_retention_by_type')
    delete_email_notifications_older_than_retention()
    mocked_notifications.assert_called_once_with('email')


def test_should_call_delete_letter_notifications_more_than_week_in_task(notify_api, mocker):
    mocked = mocker.patch('app.celery.nightly_tasks.delete_notifications_older_than_retention_by_type')
    delete_letter_notifications_older_than_retention()
    mocked.assert_called_once_with('letter')


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
        with pytest.raises(NotificationTechnicalFailureException) as e:
            timeout_notifications()
        assert str(not2.id) in str(e.value)
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


def test_timeout_notifications_sends_status_update_to_service(client, sample_template, mocker):
    callback_api = create_service_callback_api(service=sample_template.service)
    mocked = mocker.patch('app.celery.service_callback_tasks.send_delivery_status_to_service.apply_async')
    notification = create_notification(
        template=sample_template,
        status='sending',
        created_at=datetime.utcnow() - timedelta(
            seconds=current_app.config.get('SENDING_NOTIFICATIONS_TIMEOUT_PERIOD') + 10))
    timeout_notifications()

    encrypted_data = create_delivery_status_callback_data(notification, callback_api)
    mocked.assert_called_once_with([str(notification.id), encrypted_data], queue=QueueNames.CALLBACKS)


def test_send_daily_performance_stats_calls_does_not_send_if_inactive(client, mocker):
    send_mock = mocker.patch(
        'app.celery.nightly_tasks.total_sent_notifications.send_total_notifications_sent_for_day_stats')  # noqa

    with patch.object(
            PerformancePlatformClient,
            'active',
            new_callable=PropertyMock
    ) as mock_active:
        mock_active.return_value = False
        send_daily_performance_platform_stats()

    assert send_mock.call_count == 0


@freeze_time("2016-06-11 02:00:00")
def test_send_total_sent_notifications_to_performance_platform_calls_with_correct_totals(
        notify_db_session,
        sample_template,
        sample_email_template,
        mocker
):
    perf_mock = mocker.patch(
        'app.celery.nightly_tasks.total_sent_notifications.send_total_notifications_sent_for_day_stats')  # noqa

    today = date(2016, 6, 11)
    create_ft_notification_status(bst_date=today, template=sample_template)
    create_ft_notification_status(bst_date=today, template=sample_email_template)

    # Create some notifications for the day before
    yesterday = date(2016, 6, 10)
    create_ft_notification_status(bst_date=yesterday, template=sample_template, count=2)
    create_ft_notification_status(bst_date=yesterday, template=sample_email_template, count=3)

    with patch.object(
            PerformancePlatformClient,
            'active',
            new_callable=PropertyMock
    ) as mock_active:
        mock_active.return_value = True
        send_total_sent_notifications_to_performance_platform(yesterday)

        perf_mock.assert_has_calls([
            call(datetime(2016, 6, 9, 23, 0), 'sms', 2),
            call(datetime(2016, 6, 9, 23, 0), 'email', 3),
            call(datetime(2016, 6, 9, 23, 0), 'letter', 0)
        ])


def test_should_call_delete_inbound_sms(notify_api, mocker):
    mocker.patch('app.celery.nightly_tasks.delete_inbound_sms_older_than_retention')
    delete_inbound_sms()
    assert nightly_tasks.delete_inbound_sms_older_than_retention.call_count == 1


def test_create_ticket_if_letter_notifications_still_sending(mocker):
    mock_get_letters = mocker.patch(
        "app.celery.nightly_tasks.get_letter_notifications_still_sending_when_they_shouldnt_be"
    )

    mock_get_letters.return_value = 1, date(2018, 1, 15)
    mock_create_ticket = mocker.patch("app.celery.nightly_tasks.zendesk_client.create_ticket")

    raise_alert_if_letter_notifications_still_sending()

    mock_create_ticket.assert_called_once_with(
        subject="[test] Letters still sending",
        message="There are 1 letters in the 'sending' state from Monday 15 January. Resolve using https://github.com/alphagov/notifications-manuals/wiki/Support-Runbook#deal-with-letters-still-in-sending",  # noqa
        ticket_type=ZendeskClient.TYPE_INCIDENT
    )


def test_dont_create_ticket_if_letter_notifications_not_still_sending(mocker):
    mock_get_letters = mocker.patch(
        "app.celery.nightly_tasks.get_letter_notifications_still_sending_when_they_shouldnt_be"
    )

    mock_get_letters.return_value = 0, None
    mock_create_ticket = mocker.patch("app.celery.nightly_tasks.zendesk_client.create_ticket")

    raise_alert_if_letter_notifications_still_sending()

    mock_create_ticket.assert_not_called()


@freeze_time("Thursday 17th January 2018 17:00")
def test_get_letter_notifications_still_sending_when_they_shouldnt_finds_no_letters_if_sent_a_day_ago(
    sample_letter_template
):
    today = datetime.utcnow()
    one_day_ago = today - timedelta(days=1)
    create_notification(template=sample_letter_template, status='sending', sent_at=one_day_ago)

    count, expected_sent_date = get_letter_notifications_still_sending_when_they_shouldnt_be()
    assert count == 0


@freeze_time("Thursday 17th January 2018 17:00")
def test_get_letter_notifications_still_sending_when_they_shouldnt_only_finds_letters_still_in_sending_status(
    sample_letter_template
):
    two_days_ago = datetime(2018, 1, 15, 13, 30)
    create_notification(template=sample_letter_template, status='sending', sent_at=two_days_ago)
    create_notification(template=sample_letter_template, status='delivered', sent_at=two_days_ago)
    create_notification(template=sample_letter_template, status='failed', sent_at=two_days_ago)

    count, expected_sent_date = get_letter_notifications_still_sending_when_they_shouldnt_be()
    assert count == 1
    assert expected_sent_date == date(2018, 1, 15)


@freeze_time("Thursday 17th January 2018 17:00")
def test_get_letter_notifications_still_sending_when_they_shouldnt_finds_letters_older_than_offset(
    sample_letter_template
):
    three_days_ago = datetime(2018, 1, 14, 13, 30)
    create_notification(template=sample_letter_template, status='sending', sent_at=three_days_ago)

    count, expected_sent_date = get_letter_notifications_still_sending_when_they_shouldnt_be()
    assert count == 1
    assert expected_sent_date == date(2018, 1, 15)


@freeze_time("Sunday 14th January 2018 17:00")
def test_get_letter_notifications_still_sending_when_they_shouldnt_be_finds_no_letters_on_weekend(
    sample_letter_template
):
    yesterday = datetime(2018, 1, 13, 13, 30)
    create_notification(template=sample_letter_template, status='sending', sent_at=yesterday)

    count, expected_sent_date = get_letter_notifications_still_sending_when_they_shouldnt_be()
    assert count == 0


@freeze_time("Monday 15th January 2018 17:00")
def test_get_letter_notifications_still_sending_when_they_shouldnt_finds_thursday_letters_when_run_on_monday(
    sample_letter_template
):
    thursday = datetime(2018, 1, 11, 13, 30)
    yesterday = datetime(2018, 1, 14, 13, 30)
    create_notification(template=sample_letter_template, status='sending', sent_at=thursday, postage='first')
    create_notification(template=sample_letter_template, status='sending', sent_at=thursday, postage='second')
    create_notification(template=sample_letter_template, status='sending', sent_at=yesterday, postage='second')

    count, expected_sent_date = get_letter_notifications_still_sending_when_they_shouldnt_be()
    assert count == 2
    assert expected_sent_date == date(2018, 1, 11)


@freeze_time("Tuesday 16th January 2018 17:00")
def test_get_letter_notifications_still_sending_when_they_shouldnt_finds_friday_letters_when_run_on_tuesday(
    sample_letter_template
):
    friday = datetime(2018, 1, 12, 13, 30)
    yesterday = datetime(2018, 1, 14, 13, 30)
    create_notification(template=sample_letter_template, status='sending', sent_at=friday, postage='first')
    create_notification(template=sample_letter_template, status='sending', sent_at=friday, postage='second')
    create_notification(template=sample_letter_template, status='sending', sent_at=yesterday, postage='first')

    count, expected_sent_date = get_letter_notifications_still_sending_when_they_shouldnt_be()
    assert count == 2
    assert expected_sent_date == date(2018, 1, 12)


@freeze_time('2018-01-11T23:00:00')
def test_letter_raise_alert_if_no_ack_file_for_zip_does_not_raise_when_files_match_zip_list(mocker, notify_db):
    mock_file_list = mocker.patch("app.aws.s3.get_list_of_files_by_suffix", side_effect=mock_s3_get_list_match)
    letter_raise_alert_if_no_ack_file_for_zip()

    yesterday = datetime.now(tz=pytz.utc) - timedelta(days=1)  # Datatime format on AWS
    subfoldername = datetime.utcnow().strftime('%Y-%m-%d') + '/zips_sent'
    assert mock_file_list.call_count == 2
    assert mock_file_list.call_args_list == [
        call(bucket_name=current_app.config['LETTERS_PDF_BUCKET_NAME'], subfolder=subfoldername, suffix='.TXT'),
        call(bucket_name=current_app.config['DVLA_RESPONSE_BUCKET_NAME'], subfolder='root/dispatch',
             suffix='.ACK.txt', last_modified=yesterday),
    ]


@freeze_time('2018-01-11T23:00:00')
def test_letter_raise_alert_if_ack_files_not_match_zip_list(mocker, notify_db):
    mock_file_list = mocker.patch("app.aws.s3.get_list_of_files_by_suffix", side_effect=mock_s3_get_list_diff)
    mock_zendesk = mocker.patch("app.celery.nightly_tasks.zendesk_client.create_ticket")

    letter_raise_alert_if_no_ack_file_for_zip()

    assert mock_file_list.call_count == 2

    message = "Letter ack file does not contain all zip files sent. " \
              "Missing ack for zip files: {}, " \
              "pdf bucket: {}, subfolder: {}, " \
              "ack bucket: {}".format(str(['NOTIFY.2018-01-11175009', 'NOTIFY.2018-01-11175010']),
                                      current_app.config['LETTERS_PDF_BUCKET_NAME'],
                                      datetime.utcnow().strftime('%Y-%m-%d') + '/zips_sent',
                                      current_app.config['DVLA_RESPONSE_BUCKET_NAME'])
    mock_zendesk.assert_called_once_with(
        subject="Letter acknowledge error",
        message=message,
        ticket_type='incident'
    )


@freeze_time('2018-01-11T23:00:00')
def test_letter_not_raise_alert_if_no_files_do_not_cause_error(mocker, notify_db):
    mock_file_list = mocker.patch("app.aws.s3.get_list_of_files_by_suffix", side_effect=None)
    letter_raise_alert_if_no_ack_file_for_zip()

    assert mock_file_list.call_count == 2


@freeze_time('2021-01-18T02:00')
@pytest.mark.parametrize('date_provided', [None, '2021-1-17'])
def test_save_daily_notification_processing_time(mocker, sample_template, date_provided):
    # notification created too early to be counted
    create_notification(
        sample_template,
        created_at=datetime(2021, 1, 16, 23, 59),
        sent_at=datetime(2021, 1, 16, 23, 59) + timedelta(seconds=5)
    )
    # notification counted and sent within 10 seconds
    create_notification(
        sample_template,
        created_at=datetime(2021, 1, 17, 00, 00),
        sent_at=datetime(2021, 1, 17, 00, 00) + timedelta(seconds=5)
    )
    # notification counted but not sent within 10 seconds
    create_notification(
        sample_template,
        created_at=datetime(2021, 1, 17, 23, 59),
        sent_at=datetime(2021, 1, 17, 23, 59) + timedelta(seconds=15)
    )
    # notification created too late to be counted
    create_notification(
        sample_template,
        created_at=datetime(2021, 1, 18, 00, 00),
        sent_at=datetime(2021, 1, 18, 00, 00) + timedelta(seconds=5)
    )

    save_daily_notification_processing_time(date_provided)

    persisted_to_db = FactProcessingTime.query.all()
    assert len(persisted_to_db) == 1
    assert persisted_to_db[0].bst_date == date(2021, 1, 17)
    assert persisted_to_db[0].messages_total == 2
    assert persisted_to_db[0].messages_within_10_secs == 1


@freeze_time('2021-04-18T02:00')
@pytest.mark.parametrize('date_provided', [None, '2021-4-17'])
def test_save_daily_notification_processing_time_when_in_bst(mocker, sample_template, date_provided):
    # notification created too early to be counted
    create_notification(
        sample_template,
        created_at=datetime(2021, 4, 16, 22, 59),
        sent_at=datetime(2021, 4, 16, 22, 59) + timedelta(seconds=15)
    )
    # notification counted and sent within 10 seconds
    create_notification(
        sample_template,
        created_at=datetime(2021, 4, 16, 23, 00),
        sent_at=datetime(2021, 4, 16, 23, 00) + timedelta(seconds=5)
    )
    # notification counted and sent within 10 seconds
    create_notification(
        sample_template,
        created_at=datetime(2021, 4, 17, 22, 59),
        sent_at=datetime(2021, 4, 17, 22, 59) + timedelta(seconds=5)
    )
    # notification created too late to be counted
    create_notification(
        sample_template,
        created_at=datetime(2021, 4, 17, 23, 00),
        sent_at=datetime(2021, 4, 17, 23, 00) + timedelta(seconds=15)
    )

    save_daily_notification_processing_time(date_provided)

    persisted_to_db = FactProcessingTime.query.all()
    assert len(persisted_to_db) == 1
    assert persisted_to_db[0].bst_date == date(2021, 4, 17)
    assert persisted_to_db[0].messages_total == 2
    assert persisted_to_db[0].messages_within_10_secs == 2
