import pytest
import requests_mock
from requests import HTTPError
from requests.exceptions import ConnectTimeout, ReadTimeout

from app import mmg_client
from app.clients.sms import SmsClientResponseException

from app.clients.sms.mmg import get_mmg_responses, MMGClientResponseException


def test_should_return_correct_details_for_delivery():
    get_mmg_responses('3') == 'delivered'


def test_should_return_correct_details_for_temporary_failure():
    get_mmg_responses('4') == 'temporary-failure'


@pytest.mark.parametrize('status', ['5', '2'])
def test_should_return_correct_details_for_bounced(status):
    get_mmg_responses(status) == 'permanent-failure'


def test_should_be_raise_if_unrecognised_status_code():
    with pytest.raises(KeyError) as e:
        get_mmg_responses('99')
    assert '99' in str(e.value)


def test_send_sms_successful_returns_mmg_response(notify_api, mocker):
    to = content = reference = 'foo'
    response_dict = {'Reference': 12345678}

    with requests_mock.Mocker() as request_mock:
        request_mock.post('https://example.com/mmg', json=response_dict, status_code=200)
        response = mmg_client.send_sms(to, content, reference)

    response_json = response.json()
    assert response.status_code == 200
    assert response_json['Reference'] == 12345678


def test_send_sms_calls_mmg_correctly(notify_api, mocker):
    to = '+447234567890'
    content = 'my message'
    reference = 'my reference'
    response_dict = {'Reference': 12345678}

    with requests_mock.Mocker() as request_mock:
        request_mock.post('https://example.com/mmg', json=response_dict, status_code=200)
        mmg_client.send_sms(to, content, reference)

    assert request_mock.call_count == 1
    assert request_mock.request_history[0].url == 'https://example.com/mmg'
    assert request_mock.request_history[0].method == 'POST'

    request_args = request_mock.request_history[0].json()
    assert request_args['reqType'] == 'BULK'
    assert request_args['MSISDN'] == to
    assert request_args['msg'] == content
    assert request_args['sender'] == 'testing'
    assert request_args['cid'] == reference
    assert request_args['multi'] is True


def test_send_sms_raises_if_mmg_rejects(notify_api, mocker):
    to = content = reference = 'foo'
    response_dict = {
        'Error': 206,
        'Description': 'Some kind of error'
    }

    with pytest.raises(SmsClientResponseException) as exc, requests_mock.Mocker() as request_mock:
        request_mock.post('https://example.com/mmg', json=response_dict, status_code=400)
        mmg_client.send_sms(to, content, reference)

    assert exc.value.status_code == 400
    assert '"Error": 206' in exc.value.text
    assert '"Description": "Some kind of error"' in exc.value.text
    assert type(exc.value.exception) == HTTPError


def test_send_sms_override_configured_shortcode_with_sender(notify_api, mocker):
    to = '+447234567890'
    content = 'my message'
    reference = 'my reference'
    response_dict = {'Reference': 12345678}
    sender = 'fromservice'

    with requests_mock.Mocker() as request_mock:
        request_mock.post('https://example.com/mmg', json=response_dict, status_code=200)
        mmg_client.send_sms(to, content, reference, sender=sender)

    request_args = request_mock.request_history[0].json()
    assert request_args['sender'] == 'fromservice'


def test_send_sms_raises_if_mmg_fails_to_return_json(notify_api, mocker):
    to = content = reference = 'foo'
    response_dict = 'NOT AT ALL VALID JSON {"key" : "value"}}'

    with pytest.raises(SmsClientResponseException) as exc, requests_mock.Mocker() as request_mock:
        request_mock.post('https://example.com/mmg', text=response_dict, status_code=200)
        mmg_client.send_sms(to, content, reference)

    assert 'Code 200 text NOT AT ALL VALID JSON {"key" : "value"}} exception Expecting value: line 1 column 1 (char 0)' in str(exc.value)  # noqa
    assert exc.value.status_code == 200
    assert exc.value.text == 'NOT AT ALL VALID JSON {"key" : "value"}}'


def test_send_sms_raises_if_mmg_rejects_with_connect_timeout(rmock):
    to = content = reference = 'foo'

    with pytest.raises(MMGClientResponseException) as exc:
        rmock.register_uri('POST', 'https://example.com/mmg', exc=ConnectTimeout)
        mmg_client.send_sms(to, content, reference)

    assert exc.value.status_code == 504
    assert exc.value.text == 'Gateway Time-out'


def test_send_sms_raises_if_mmg_rejects_with_read_timeout(rmock):
    to = content = reference = 'foo'

    with pytest.raises(MMGClientResponseException) as exc:
        rmock.register_uri('POST', 'https://example.com/mmg', exc=ReadTimeout)
        mmg_client.send_sms(to, content, reference)

    assert exc.value.status_code == 504
    assert exc.value.text == 'Gateway Time-out'
