import requests_mock
import pytest
from datetime import datetime
from freezegun import freeze_time
from functools import partial

from app.clients.performance_platform.performance_platform_client import PerformancePlatformClient
from app.utils import (
    get_london_midnight_in_utc,
    get_midnight_for_day_before
)
from tests.app.conftest import sample_notification_history as create_notification_history


@pytest.fixture(scope='function')
def client(mocker):
    client = PerformancePlatformClient()
    current_app = mocker.Mock(config={
        'PERFORMANCE_PLATFORM_ENABLED': True,
        'PERFORMANCE_PLATFORM_URL': 'https://performance-platform-url/',
        'PERFORMANCE_PLATFORM_TOKEN': 'token'
    })
    client.init_app(current_app)
    return client


def test_should_not_call_if_not_enabled(notify_api, client, mocker):
    mocker.patch.object(client, '_send_stats_to_performance_platform')
    client.active = False
    client.send_performance_stats(
        date=datetime(2016, 10, 16, 0, 0, 0),
        channel='sms',
        count=142,
        period='day'
    )

    client._send_stats_to_performance_platform.assert_not_called()


def test_should_call_if_enabled(notify_api, client, mocker):
    mocker.patch.object(client, '_send_stats_to_performance_platform')
    client.send_performance_stats(
        date=datetime(2016, 10, 16, 0, 0, 0),
        channel='sms',
        count=142,
        period='day'
    )

    assert client._send_stats_to_performance_platform.call_count == 1


def test_send_platform_stats_creates_correct_call(notify_api, client):
    with requests_mock.Mocker() as request_mock:
        request_mock.post(
            client.performance_platform_url,
            json={},
            status_code=200
        )
        client.send_performance_stats(
            date=datetime(2016, 10, 16, 0, 0, 0),
            channel='sms',
            count=142,
            period='day'
        )

    assert request_mock.call_count == 1

    assert request_mock.request_history[0].url == client.performance_platform_url
    assert request_mock.request_history[0].method == 'POST'

    request_args = request_mock.request_history[0].json()
    assert request_args['dataType'] == 'notifications'
    assert request_args['service'] == 'govuk-notify'
    assert request_args['period'] == 'day'
    assert request_args['channel'] == 'sms'
    assert request_args['_timestamp'] == '2016-10-16T00:00:00'
    assert request_args['count'] == 142
    expected_base64_id = 'MjAxNi0xMC0xNlQwMDowMDowMGdvdnVrLW5vdGlmeXNtc25vdGlmaWNhdGlvbnNkYXk='
    assert request_args['_id'] == expected_base64_id


@freeze_time("2016-01-11 12:30:00")
def test_get_total_sent_notifications_yesterday_returns_expected_totals_dict(
    notify_db,
    notify_db_session,
    client,
    sample_template
):
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

    total_count_dict = client.get_total_sent_notifications_yesterday()

    assert total_count_dict == {
        "start_date": get_midnight_for_day_before(datetime.utcnow()),
        "email": {
            "count": 3
        },
        "sms": {
            "count": 2
        }
    }
