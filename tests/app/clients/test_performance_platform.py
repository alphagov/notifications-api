import pytest
import requests
import requests_mock

from app.clients.performance_platform.performance_platform_client import (
    PerformancePlatformClient,
)


@pytest.fixture(scope='function')
def perf_client(client, mocker):
    perf_client = PerformancePlatformClient()
    current_app = mocker.Mock(config={
        'PERFORMANCE_PLATFORM_ENABLED': True,
        'PERFORMANCE_PLATFORM_ENDPOINTS': {
            'foo': 'my_token',
            'bar': 'other_token'
        },
        'PERFORMANCE_PLATFORM_URL': 'https://performance-platform-url/'
    })
    perf_client.init_app(current_app)
    return perf_client


def test_should_not_call_if_not_enabled(perf_client):
    with requests_mock.Mocker() as request_mock:
        request_mock.post('https://performance-platform-url/foo', json={}, status_code=200)
        perf_client._active = False
        perf_client.send_stats_to_performance_platform({'dataType': 'foo'})

    assert request_mock.called is False


def test_should_call_datatype_endpoint_if_enabled(perf_client):
    with requests_mock.Mocker() as request_mock:
        request_mock.post('https://performance-platform-url/foo', json={}, status_code=200)
        perf_client.send_stats_to_performance_platform({'dataType': 'foo'})

    assert request_mock.call_count == 1
    assert request_mock.last_request.method == 'POST'


@pytest.mark.parametrize('dataset, token', [
    ('foo', 'my_token'),
    ('bar', 'other_token')
])
def test_should_use_correct_token(perf_client, dataset, token):
    with requests_mock.Mocker() as request_mock:
        request_mock.post('https://performance-platform-url/foo', json={}, status_code=200)
        request_mock.post('https://performance-platform-url/bar', json={}, status_code=200)
        perf_client.send_stats_to_performance_platform({'dataType': dataset})

    assert request_mock.call_count == 1
    assert request_mock.last_request.headers.get('authorization') == 'Bearer {}'.format(token)


def test_should_raise_for_status(perf_client):
    with pytest.raises(requests.HTTPError), requests_mock.Mocker() as request_mock:
        request_mock.post('https://performance-platform-url/foo', json={}, status_code=403)
        perf_client.send_stats_to_performance_platform({'dataType': 'foo'})
