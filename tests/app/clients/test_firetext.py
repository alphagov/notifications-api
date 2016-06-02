from urllib.parse import parse_qs

import pytest
import requests_mock

from app.clients.sms.firetext import (get_firetext_responses, FiretextClientException)


def test_should_return_correct_details_for_delivery():
    response_dict = get_firetext_responses('0')
    assert response_dict['message'] == 'Delivered'
    assert response_dict['notification_status'] == 'delivered'
    assert response_dict['notification_statistics_status'] == 'delivered'
    assert response_dict['success']


def test_should_return_correct_details_for_bounced():
    response_dict = get_firetext_responses('1')
    assert response_dict['message'] == 'Declined'
    assert response_dict['notification_status'] == 'permanent-failure'
    assert response_dict['notification_statistics_status'] == 'failure'
    assert not response_dict['success']


def test_should_return_correct_details_for_complaint():
    response_dict = get_firetext_responses('2')
    assert response_dict['message'] == 'Undelivered (Pending with Network)'
    assert response_dict['notification_status'] == 'pending'
    assert response_dict['notification_statistics_status'] is None
    assert response_dict['success']


def test_should_be_none_if_unrecognised_status_code():
    with pytest.raises(KeyError) as e:
        get_firetext_responses('99')
    assert '99' in str(e.value)


def test_send_sms_successful_returns_firetext_response(mocker, mock_firetext_client):
    to = content = reference = 'foo'
    response_dict = {
        'data': [],
        'description': 'SMS successfully queued',
        'code': 0,
        'responseData': 1
    }

    with requests_mock.Mocker() as request_mock:
        request_mock.post('https://www.firetext.co.uk/api/sendsms/json', json=response_dict, status_code=200)
        response = mock_firetext_client.send_sms(to, content, reference)

    response_json = response.json()
    assert response.status_code == 200
    assert response_json['code'] == 0
    assert response_json['description'] == 'SMS successfully queued'


def test_send_sms_calls_firetext_correctly(mocker, mock_firetext_client):
    to = '+447234567890'
    content = 'my message'
    reference = 'my reference'
    response_dict = {
        'code': 0,
    }

    with requests_mock.Mocker() as request_mock:
        request_mock.post('https://www.firetext.co.uk/api/sendsms/json', json=response_dict, status_code=200)
        mock_firetext_client.send_sms(to, content, reference)

    assert request_mock.call_count == 1
    assert request_mock.request_history[0].url == 'https://www.firetext.co.uk/api/sendsms/json'
    assert request_mock.request_history[0].method == 'POST'

    request_args = parse_qs(request_mock.request_history[0].text)
    assert request_args['apiKey'][0] == 'foo'
    assert request_args['from'][0] == 'bar'
    assert request_args['to'][0] == '447234567890'
    assert request_args['message'][0] == content
    assert request_args['reference'][0] == reference


def test_send_sms_raises_if_firetext_rejects(mocker, mock_firetext_client):
    to = content = reference = 'foo'
    response_dict = {
        'data': [],
        'description': 'Some kind of error',
        'code': 1,
        'responseData': ''
    }

    with pytest.raises(FiretextClientException) as exc, requests_mock.Mocker() as request_mock:
        request_mock.post('https://www.firetext.co.uk/api/sendsms/json', json=response_dict, status_code=200)
        mock_firetext_client.send_sms(to, content, reference)

    assert exc.value.code == 1
    assert exc.value.description == 'Some kind of error'
