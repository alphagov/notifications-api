import pytest
import requests_mock
from requests.exceptions import ConnectTimeout, ReadTimeout

from app import reach_client
from app.clients.sms import SmsClientResponseException

# TODO: tests for get_reach_responses


def test_try_send_sms_successful_returns_reach_response(notify_api, mocker):
    to = content = reference = 'foo'
    response_dict = {}  # TODO

    with requests_mock.Mocker() as request_mock:
        request_mock.post('https://example.com/reach', json=response_dict, status_code=200)
        response = reach_client.try_send_sms(to, content, reference, False, 'sender')

    # response_json = response.json()
    assert response.status_code == 200
    # TODO: assertions


def test_try_send_sms_calls_reach_correctly(notify_api, mocker):
    to = '+447234567890'
    content = 'my message'
    reference = 'my reference'
    response_dict = {}  # TODO

    with requests_mock.Mocker() as request_mock:
        request_mock.post('https://example.com/reach', json=response_dict, status_code=200)
        reach_client.try_send_sms(to, content, reference, False, 'sender')

    assert request_mock.call_count == 1
    assert request_mock.request_history[0].url == 'https://example.com/reach'
    assert request_mock.request_history[0].method == 'POST'

    # request_args = request_mock.request_history[0].json()
    # TODO: assertions


def test_try_send_sms_raises_if_reach_rejects(notify_api, mocker):
    to = content = reference = 'foo'
    response_dict = {
        'Error': 206,
        'Description': 'Some kind of error'
    }

    with pytest.raises(SmsClientResponseException) as exc, requests_mock.Mocker() as request_mock:
        request_mock.post('https://example.com/reach', json=response_dict, status_code=400)
        reach_client.try_send_sms(to, content, reference, False, 'sender')

    assert "Request failed" in str(exc)


def test_try_send_sms_raises_if_reach_fails_to_return_json(notify_api, mocker):
    to = content = reference = 'foo'
    response_dict = 'NOT AT ALL VALID JSON {"key" : "value"}}'

    with pytest.raises(SmsClientResponseException) as exc, requests_mock.Mocker() as request_mock:
        request_mock.post('https://example.com/reach', text=response_dict, status_code=200)
        reach_client.try_send_sms(to, content, reference, False, 'sender')

    assert 'Invalid response JSON' in str(exc.value)


def test_try_send_sms_raises_if_reach_rejects_with_connect_timeout(rmock):
    to = content = reference = 'foo'

    with pytest.raises(SmsClientResponseException) as exc:
        rmock.register_uri('POST', 'https://example.com/reach', exc=ConnectTimeout)
        reach_client.try_send_sms(to, content, reference, False, 'sender')

    assert 'Request failed' in str(exc.value)


def test_try_send_sms_raises_if_reach_rejects_with_read_timeout(rmock):
    to = content = reference = 'foo'

    with pytest.raises(SmsClientResponseException) as exc:
        rmock.register_uri('POST', 'https://example.com/reach', exc=ReadTimeout)
        reach_client.try_send_sms(to, content, reference, False, 'sender')

    assert 'Request failed' in str(exc.value)
