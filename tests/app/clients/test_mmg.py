import pytest
import requests_mock
from requests.exceptions import ConnectTimeout, ReadTimeout

from app import mmg_client
from app.clients.sms.mmg import SmsClientResponseException, get_mmg_responses


@pytest.mark.parametrize(
    "detailed_status_code, result", [(None, ("delivered", None)), ("5", ("delivered", "Delivered to handset"))]
)
def test_get_mmg_responses_should_return_correct_details_for_delivery(detailed_status_code, result):
    assert get_mmg_responses("3", detailed_status_code) == result


@pytest.mark.parametrize(
    "detailed_status_code, result", [(None, ("temporary-failure", None)), ("15", ("temporary-failure", "Expired"))]
)
def test_get_mmg_responses_should_return_correct_details_for_temporary_failure(detailed_status_code, result):
    assert get_mmg_responses("4", detailed_status_code) == result


@pytest.mark.parametrize(
    "status, detailed_status_code, result",
    [
        ("2", None, ("permanent-failure", None)),
        ("2", "12", ("permanent-failure", "Illegal equipment")),
        ("5", None, ("permanent-failure", None)),
        ("5", "20", ("permanent-failure", "Rejected by anti-flooding mechanism")),
    ],
)
def test_get_mmg_responses_should_return_correct_details_for_bounced(status, detailed_status_code, result):
    assert get_mmg_responses(status, detailed_status_code) == result


def test_get_mmg_responses_raises_KeyError_if_unrecognised_status_code():
    with pytest.raises(KeyError) as e:
        get_mmg_responses("99")
    assert "99" in str(e.value)


def test_try_send_sms_successful_returns_mmg_response(notify_api, mocker):
    to = content = reference = "foo"
    response_dict = {"Reference": 12345678}

    with requests_mock.Mocker() as request_mock:
        request_mock.post("https://example.com/mmg", json=response_dict, status_code=200)
        response = mmg_client.try_send_sms(to, content, reference, False, "sender")

    response_json = response.json()
    assert response.status_code == 200
    assert response_json["Reference"] == 12345678


def test_try_send_sms_successful_with_custom_receipts(notify_api, mock_mmg_client_with_receipts):
    to = content = reference = "foo"
    response_dict = {"Reference": 12345678}

    with requests_mock.Mocker() as request_mock:
        request_mock.post("https://example.com/mmg", json=response_dict, status_code=200)
        mock_mmg_client_with_receipts.try_send_sms(to, content, reference, False, "sender")

    request_args = request_mock.request_history[0].json()
    assert request_args["delurl"] == "https://www.example.com/notifications/sms/mmg"


def test_try_send_sms_calls_mmg_correctly(notify_api, mocker):
    to = "+447234567890"
    content = "my message"
    reference = "my reference"
    response_dict = {"Reference": 12345678}

    with requests_mock.Mocker() as request_mock:
        request_mock.post("https://example.com/mmg", json=response_dict, status_code=200)
        mmg_client.try_send_sms(to, content, reference, False, "testing")

    assert request_mock.call_count == 1
    assert request_mock.request_history[0].url == "https://example.com/mmg"
    assert request_mock.request_history[0].method == "POST"

    request_args = request_mock.request_history[0].json()
    assert request_args["reqType"] == "BULK"
    assert request_args["MSISDN"] == to
    assert request_args["msg"] == content
    assert request_args["sender"] == "testing"
    assert request_args["cid"] == reference
    assert request_args["multi"] is True
    assert "delurl" not in request_args


def test_try_send_sms_raises_if_mmg_rejects(notify_api, mocker):
    to = content = reference = "foo"
    response_dict = {"Error": 206, "Description": "Some kind of error"}

    with pytest.raises(SmsClientResponseException) as exc, requests_mock.Mocker() as request_mock:
        request_mock.post("https://example.com/mmg", json=response_dict, status_code=400)
        mmg_client.try_send_sms(to, content, reference, False, "sender")

    assert "Request failed" in str(exc.value)


def test_try_send_sms_raises_if_mmg_fails_to_return_json(notify_api, mocker):
    to = content = reference = "foo"
    response_dict = 'NOT AT ALL VALID JSON {"key" : "value"}}'

    with pytest.raises(SmsClientResponseException) as exc, requests_mock.Mocker() as request_mock:
        request_mock.post("https://example.com/mmg", text=response_dict, status_code=200)
        mmg_client.try_send_sms(to, content, reference, False, "sender")

    assert "Invalid response JSON" in str(exc.value)


def test_try_send_sms_raises_if_mmg_rejects_with_connect_timeout(rmock):
    to = content = reference = "foo"

    with pytest.raises(SmsClientResponseException) as exc:
        rmock.register_uri("POST", "https://example.com/mmg", exc=ConnectTimeout)
        mmg_client.try_send_sms(to, content, reference, False, "sender")

    assert "Request failed" in str(exc.value)


def test_try_send_sms_raises_if_mmg_rejects_with_read_timeout(rmock):
    to = content = reference = "foo"

    with pytest.raises(SmsClientResponseException) as exc:
        rmock.register_uri("POST", "https://example.com/mmg", exc=ReadTimeout)
        mmg_client.try_send_sms(to, content, reference, False, "sender")

    assert "Request failed" in str(exc.value)
