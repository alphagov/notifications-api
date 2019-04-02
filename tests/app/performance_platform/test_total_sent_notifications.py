from datetime import datetime, date

from freezegun import freeze_time

from app.performance_platform.total_sent_notifications import (
    send_total_notifications_sent_for_day_stats,
    get_total_sent_notifications_for_day
)

from tests.app.db import create_template, create_ft_notification_status


def test_send_total_notifications_sent_for_day_stats_stats_creates_correct_call(mocker, client):
    send_stats = mocker.patch('app.performance_platform.total_sent_notifications.performance_platform_client.send_stats_to_performance_platform')  # noqa

    send_total_notifications_sent_for_day_stats(
        start_time=datetime(2016, 10, 15, 23, 0, 0),
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


@freeze_time('2018-06-10 01:00')
def test_get_total_sent_notifications_yesterday_returns_expected_totals_dict(sample_service):
    sms = create_template(sample_service, template_type='sms')
    email = create_template(sample_service, template_type='email')
    letter = create_template(sample_service, template_type='letter')

    today = date(2018, 6, 10)
    yesterday = date(2018, 6, 9)

    # todays is excluded
    create_ft_notification_status(bst_date=today, template=sms)
    create_ft_notification_status(bst_date=today, template=email)
    create_ft_notification_status(bst_date=today, template=letter)

    # yesterdays is included
    create_ft_notification_status(bst_date=yesterday, template=sms, count=2)
    create_ft_notification_status(bst_date=yesterday, template=email, count=3)
    create_ft_notification_status(bst_date=yesterday, template=letter, count=1)

    total_count_dict = get_total_sent_notifications_for_day(yesterday)

    assert total_count_dict == {
        "email": 3,
        "sms": 2,
        "letter": 1
    }
