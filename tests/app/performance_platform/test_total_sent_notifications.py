from datetime import datetime, timedelta

from app.performance_platform.total_sent_notifications import (
    send_total_notifications_sent_for_day_stats,
    get_total_sent_notifications_for_day
)

from tests.app.db import create_template, create_ft_notification_status


def test_send_total_notifications_sent_for_day_stats_stats_creates_correct_call(mocker, client):
    send_stats = mocker.patch('app.performance_platform.total_sent_notifications.performance_platform_client.send_stats_to_performance_platform')  # noqa

    send_total_notifications_sent_for_day_stats(
        date=datetime(2016, 10, 15, 23, 0, 0),
        notification_type='sms',
        count=142
    )

    assert send_stats.call_count == 1

    request_args = send_stats.call_args[0][0]
    assert request_args['dataType'] == 'notifications'
    assert request_args['service'] == 'govuk-notify'
    assert request_args['period'] == 'day'
    assert request_args['channel'] == 'sms'
    assert request_args['_timestamp'] == '2016-10-16T00:00:00'
    assert request_args['count'] == 142
    expected_base64_id = 'MjAxNi0xMC0xNlQwMDowMDowMGdvdnVrLW5vdGlmeXNtc25vdGlmaWNhdGlvbnNkYXk='
    assert request_args['_id'] == expected_base64_id


def test_get_total_sent_notifications_yesterday_returns_expected_totals_dict(sample_service):
    sms = create_template(sample_service, template_type='sms')
    email = create_template(sample_service, template_type='email')
    letter = create_template(sample_service, template_type='letter')

    today = datetime.utcnow().date()
    yesterday = today - timedelta(days=1)
    create_ft_notification_status(bst_date=today, notification_type='sms',
                                  service=sms.service, template=sms)
    create_ft_notification_status(bst_date=today, notification_type='email',
                                  service=email.service, template=email)
    create_ft_notification_status(bst_date=today, notification_type='letter',
                                  service=letter.service, template=letter)

    create_ft_notification_status(bst_date=yesterday, notification_type='sms',
                                  service=sms.service, template=sms, count=2)
    create_ft_notification_status(bst_date=yesterday, notification_type='email',
                                  service=email.service, template=email, count=3)
    create_ft_notification_status(bst_date=yesterday, notification_type='letter',
                                  service=letter.service, template=letter, count=1)

    total_count_dict = get_total_sent_notifications_for_day(yesterday)

    assert total_count_dict["email"] == {"count": 3}
    assert total_count_dict["sms"] == {"count": 2}
    assert total_count_dict["letter"] == {"count": 1}

    # Should return a time around midnight depending on timezones
    expected_start = datetime.combine(yesterday, datetime.min.time())
    time_diff = abs(expected_start - total_count_dict["start_date"])
    assert time_diff <= timedelta(minutes=60)
