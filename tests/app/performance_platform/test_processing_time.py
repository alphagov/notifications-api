from datetime import datetime, timedelta

from freezegun import freeze_time

from tests.app.db import create_notification
from app.performance_platform.processing_time import (
    send_processing_time_to_performance_platform,
    send_processing_time_data
)


@freeze_time('2016-10-18T02:00')
def test_send_processing_time_to_performance_platform_generates_correct_calls(mocker, sample_template):
    send_mock = mocker.patch('app.performance_platform.processing_time.send_processing_time_data')

    created_at = datetime.utcnow() - timedelta(days=1)

    create_notification(sample_template, created_at=created_at, sent_at=created_at + timedelta(seconds=5))
    create_notification(sample_template, created_at=created_at, sent_at=created_at + timedelta(seconds=15))
    create_notification(sample_template, created_at=datetime.utcnow() - timedelta(days=2))

    send_processing_time_to_performance_platform()

    send_mock.assert_any_call(datetime(2016, 10, 16, 23, 0), 'messages-total', 2)
    send_mock.assert_any_call(datetime(2016, 10, 16, 23, 0), 'messages-within-10-secs', 1)


def test_send_processing_time_to_performance_platform_creates_correct_call_to_perf_platform(mocker):
    send_stats = mocker.patch('app.performance_platform.total_sent_notifications.performance_platform_client.send_stats_to_performance_platform')  # noqa

    send_processing_time_data(
        start_time=datetime(2016, 10, 15, 23, 0, 0),
        status='foo',
        count=142
    )

    assert send_stats.call_count == 1

    request_args = send_stats.call_args[0][0]
    assert request_args['dataType'] == 'processing-time'
    assert request_args['service'] == 'govuk-notify'
    assert request_args['period'] == 'day'
    assert request_args['status'] == 'foo'
    assert request_args['_timestamp'] == '2016-10-16T00:00:00'
    assert request_args['count'] == 142
    expected_base64_id = 'MjAxNi0xMC0xNlQwMDowMDowMGdvdnVrLW5vdGlmeWZvb3Byb2Nlc3NpbmctdGltZWRheQ=='
    assert request_args['_id'] == expected_base64_id
