from datetime import datetime

from freezegun import freeze_time

from app.utils import get_midnight_for_day_before
from app.performance_platform.total_sent_notifications import (
    send_total_notifications_sent_for_day_stats,
    get_total_sent_notifications_for_day
)

from tests.app.db import create_template, create_notification


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


@freeze_time("2016-01-11 12:30:00")
def test_get_total_sent_notifications_yesterday_returns_expected_totals_dict(sample_service):
    sms = create_template(sample_service, template_type='sms')
    email = create_template(sample_service, template_type='email')
    letter = create_template(sample_service, template_type='letter')

    create_notification(email, status='delivered')
    create_notification(sms, status='delivered')

    # Create some notifications for the day before
    yesterday = datetime(2016, 1, 10, 15, 30, 0, 0)
    ereyesterday = datetime(2016, 1, 9, 15, 30, 0, 0)
    with freeze_time(yesterday):
        create_notification(letter, status='delivered')
        create_notification(sms, status='delivered')
        create_notification(sms, status='delivered')
        create_notification(email, status='delivered')
        create_notification(email, status='delivered')
        create_notification(email, status='delivered')

    total_count_dict = get_total_sent_notifications_for_day(yesterday)

    assert total_count_dict == {
        "start_date": get_midnight_for_day_before(datetime.utcnow()),
        "email": {
            "count": 3
        },
        "sms": {
            "count": 2
        },
        "letter": {
            "count": 1
        }
    }

    another_day = get_total_sent_notifications_for_day(ereyesterday)

    assert another_day == {
        'email': {'count': 0},
        'letter': {'count': 0},
        'sms': {'count': 0},
        'start_date': datetime(2016, 1, 9, 0, 0),
    }
