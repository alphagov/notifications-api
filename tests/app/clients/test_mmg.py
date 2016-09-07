import pytest
import requests_mock
from app import mmg_client

from app.clients.sms.mmg import (get_mmg_responses, MMGClientException)


def test_should_return_correct_details_for_delivery():
    response_dict = get_mmg_responses('3')
    assert response_dict['message'] == 'Delivered'
    assert response_dict['notification_status'] == 'delivered'
    assert response_dict['notification_statistics_status'] == 'delivered'
    assert response_dict['success']


def test_should_return_correct_details_for_bounced():
    response_dict = get_mmg_responses('50')
    assert response_dict['message'] == 'Declined'
    assert response_dict['notification_status'] == 'failed'
    assert response_dict['notification_statistics_status'] == 'failure'
    assert not response_dict['success']


def test_should_be_none_if_unrecognised_status_code():
    response_dict = get_mmg_responses('blah')
    assert response_dict['message'] == 'Declined'
    assert response_dict['notification_status'] == 'failed'
    assert response_dict['notification_statistics_status'] == 'failure'
    assert not response_dict['success']


def test_send_sms_successful_returns_mmg_response(notify_api, mocker):
    to = content = reference = 'foo'
    response_dict = {'Reference': 12345678}

    with requests_mock.Mocker() as request_mock:
        request_mock.post('https://api.mmg.co.uk/json/api.php', json=response_dict, status_code=200)
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
        request_mock.post('https://api.mmg.co.uk/json/api.php', json=response_dict, status_code=200)
        mmg_client.send_sms(to, content, reference)

    assert request_mock.call_count == 1
    assert request_mock.request_history[0].url == 'https://api.mmg.co.uk/json/api.php'
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

    with pytest.raises(MMGClientException) as exc, requests_mock.Mocker() as request_mock:
        request_mock.post('https://api.mmg.co.uk/json/api.php', json=response_dict, status_code=400)
        mmg_client.send_sms(to, content, reference)

    assert exc.value.code == 206
    assert exc.value.description == 'Some kind of error'


def test_send_sms_override_configured_shortcode_with_sender(notify_api, mocker):
    to = '+447234567890'
    content = 'my message'
    reference = 'my reference'
    response_dict = {'Reference': 12345678}
    sender = 'fromservice'

    with requests_mock.Mocker() as request_mock:
        request_mock.post('https://api.mmg.co.uk/json/api.php', json=response_dict, status_code=200)
        mmg_client.send_sms(to, content, reference, sender=sender)

    request_args = request_mock.request_history[0].json()
    assert request_args['sender'] == 'fromservice'
