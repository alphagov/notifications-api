from unittest.mock import Mock
from urllib.parse import parse_qs

import pytest
import requests_mock
from requests.exceptions import ConnectTimeout, ReadTimeout

from app.clients.sms.firetext import FiretextClient, SmsClientResponseException, get_firetext_responses


@pytest.fixture(scope="function")
def mock_firetext_configured_app():
    config = {
        "FIRETEXT_URL": "https://example.com/firetext",
        "FIRETEXT_API_KEY": "foo",
        "FIRETEXT_INTERNATIONAL_API_KEY": "international",
        "FROM_NUMBER": "bar",
    }
    return Mock(config=config)


@pytest.mark.parametrize(
    "detailed_status_code, result", [(None, ("delivered", None)), ("000", ("delivered", "No error reported"))]
)
def test_get_firetext_responses_should_return_correct_details_for_delivery(detailed_status_code, result):
    assert get_firetext_responses("0", detailed_status_code) == result


@pytest.mark.parametrize(
    "detailed_status_code, result",
    [(None, ("permanent-failure", None)), ("401", ("permanent-failure", "Message Rejected"))],
)
def test_get_firetext_responses_should_return_correct_details_for_bounced(detailed_status_code, result):
    assert get_firetext_responses("1", detailed_status_code) == result


def test_get_firetext_responses_should_return_correct_details_for_complaint():
    assert get_firetext_responses("2") == ("pending", None)


def test_get_firetext_responses_raises_KeyError_if_unrecognised_status_code():
    with pytest.raises(KeyError) as e:
        get_firetext_responses("99")
    assert "99" in str(e.value)


def test_try_send_sms_successful_returns_firetext_response(mock_firetext_configured_app):
    firetext_client = FiretextClient(mock_firetext_configured_app)

    to = content = reference = "foo"
    response_dict = {"data": [], "description": "SMS successfully queued", "code": 0, "responseData": 1}

    with requests_mock.Mocker() as request_mock:
        request_mock.post("https://example.com/firetext", json=response_dict, status_code=200)
        response = firetext_client.try_send_sms(to, content, reference, False, "sender")

    response_json = response.json()
    assert response.status_code == 200
    assert response_json["code"] == 0
    assert response_json["description"] == "SMS successfully queued"


def test_try_send_sms_calls_firetext_correctly(mock_firetext_configured_app):
    firetext_client = FiretextClient(mock_firetext_configured_app)

    to = "+447234567890"
    content = "my message"
    reference = "my reference"
    response_dict = {
        "code": 0,
    }

    with requests_mock.Mocker() as request_mock:
        request_mock.post("https://example.com/firetext", json=response_dict, status_code=200)
        firetext_client.try_send_sms(to, content, reference, False, "bar")

    assert request_mock.call_count == 1
    assert request_mock.request_history[0].url == "https://example.com/firetext"
    assert request_mock.request_history[0].method == "POST"

    request_args = parse_qs(request_mock.request_history[0].text)
    assert request_args["apiKey"][0] == "foo"
    assert request_args["from"][0] == "bar"
    assert request_args["to"][0] == "447234567890"
    assert request_args["message"][0] == content
    assert request_args["reference"][0] == reference
    assert "receipt" not in request_args


@pytest.mark.parametrize("basic_auth_credentials", (None, ("foo123", "foo321")))
def test_try_send_sms_calls_firetext_correctly_with_receipts(mock_firetext_configured_app, basic_auth_credentials):
    mock_firetext_configured_app.config.update(
        {
            "FIRETEXT_RECEIPT_URL": "https://www.example.com:1234/notifications/sms/firetext",
            "FIRETEXT_DELIVERY_STATUS_CALLBACK_BASIC_AUTH_CREDENTIALS": basic_auth_credentials,
        }
    )
    firetext_client = FiretextClient(mock_firetext_configured_app)

    to = content = reference = "foo"
    response_dict = {
        "code": 0,
    }

    with requests_mock.Mocker() as request_mock:
        request_mock.post("https://example.com/firetext", json=response_dict, status_code=200)
        firetext_client.try_send_sms(to, content, reference, False, "bar")

    assert len(request_mock.request_history) == 1
    request_args = parse_qs(request_mock.request_history[0].text)
    if basic_auth_credentials is None:
        assert request_args["receipt"][0] == "https://www.example.com:1234/notifications/sms/firetext"
    else:
        assert (
            request_args["receipt"][0]
            == f"https://{':'.join(basic_auth_credentials)}@www.example.com:1234/notifications/sms/firetext"
        )


def test_try_send_sms_calls_firetext_correctly_for_international(mocker, mock_firetext_configured_app):
    firetext_client = FiretextClient(mock_firetext_configured_app)

    to = "+607234567890"
    content = "my message"
    reference = "my reference"
    response_dict = {
        "code": 0,
    }

    with requests_mock.Mocker() as request_mock:
        request_mock.post("https://example.com/firetext", json=response_dict, status_code=200)
        firetext_client.try_send_sms(to, content, reference, True, "bar")

    assert request_mock.call_count == 1
    assert request_mock.request_history[0].url == "https://example.com/firetext"
    assert request_mock.request_history[0].method == "POST"

    request_args = parse_qs(request_mock.request_history[0].text)
    assert request_args["apiKey"][0] == "international"
    assert request_args["from"][0] == "bar"
    assert request_args["to"][0] == "607234567890"
    assert request_args["message"][0] == content
    assert request_args["reference"][0] == reference


def test_try_send_sms_raises_if_firetext_rejects(mocker, mock_firetext_configured_app):
    firetext_client = FiretextClient(mock_firetext_configured_app)

    to = content = reference = "foo"
    response_dict = {"data": [], "description": "Some kind of error", "code": 1, "responseData": ""}

    with pytest.raises(SmsClientResponseException) as exc, requests_mock.Mocker() as request_mock:
        request_mock.post("https://example.com/firetext", json=response_dict, status_code=200)
        firetext_client.try_send_sms(to, content, reference, False, "sender")

    assert "Invalid response JSON" in str(exc.value)


def test_try_send_sms_raises_if_firetext_rejects_with_unexpected_data(mocker, mock_firetext_configured_app):
    firetext_client = FiretextClient(mock_firetext_configured_app)

    to = content = reference = "foo"
    response_dict = {"something": "gone bad"}

    with pytest.raises(SmsClientResponseException) as exc, requests_mock.Mocker() as request_mock:
        request_mock.post("https://example.com/firetext", json=response_dict, status_code=400)
        firetext_client.try_send_sms(to, content, reference, False, "sender")

    assert "Request failed" in str(exc.value)


def test_try_send_sms_raises_if_firetext_fails_to_return_json(notify_api, mock_firetext_configured_app):
    firetext_client = FiretextClient(mock_firetext_configured_app)

    to = content = reference = "foo"
    response_dict = 'NOT AT ALL VALID JSON {"key" : "value"}}'

    with pytest.raises(SmsClientResponseException) as exc, requests_mock.Mocker() as request_mock:
        request_mock.post("https://example.com/firetext", text=response_dict, status_code=200)
        firetext_client.try_send_sms(to, content, reference, False, "sender")

    assert "Invalid response JSON" in str(exc.value)


def test_try_send_sms_raises_if_firetext_rejects_with_connect_timeout(rmock, mock_firetext_configured_app):
    firetext_client = FiretextClient(mock_firetext_configured_app)

    to = content = reference = "foo"

    with pytest.raises(SmsClientResponseException) as exc:
        rmock.register_uri("POST", "https://example.com/firetext", exc=ConnectTimeout)
        firetext_client.try_send_sms(to, content, reference, False, "sender")

    assert "Request failed" in str(exc.value)


def test_try_send_sms_raises_if_firetext_rejects_with_read_timeout(rmock, mock_firetext_configured_app):
    firetext_client = FiretextClient(mock_firetext_configured_app)

    to = content = reference = "foo"

    with pytest.raises(SmsClientResponseException) as exc:
        rmock.register_uri("POST", "https://example.com/firetext", exc=ReadTimeout)
        firetext_client.try_send_sms(to, content, reference, False, "sender")

    assert "Request failed" in str(exc.value)
