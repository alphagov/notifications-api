import socket
import ssl
import string
import sys
import time
from collections import namedtuple
from datetime import datetime
from unittest.mock import Mock

import boto3
import freezegun
import jwt
import pytest
import pytz
import requests
import trustme
from flask import current_app
from moto import mock_ssm
from notifications_utils.postal_address import PostalAddress
from redis.exceptions import LockError

from app.clients.letter.dvla import (
    DVLAClient,
    DvlaDuplicatePrintRequestException,
    DvlaException,
    DvlaNonRetryableException,
    DvlaRetryableException,
    DvlaThrottlingException,
    DvlaUnauthorisedRequestException,
    SSMParameter,
)


@pytest.fixture
def ssm():
    with mock_ssm():
        ssm_client = boto3.client("ssm", "eu-west-1")
        ssm_client.put_parameter(
            Name="/notify/api/dvla_username",
            Value="some username",
            Type="SecureString",
        )
        ssm_client.put_parameter(
            Name="/notify/api/dvla_password",
            Value="some password",
            Type="SecureString",
        )
        ssm_client.put_parameter(
            Name="/notify/api/dvla_api_key",
            Value="some api key",
            Type="SecureString",
        )
        yield ssm_client


@pytest.fixture
def dvla_client(notify_api, client, ssm):
    dvla_client = DVLAClient()
    dvla_client.init_app(notify_api, statsd_client=Mock())
    yield dvla_client


@pytest.fixture
def dvla_authenticate(rmock):
    token = jwt.encode(payload={"exp": int(time.time())}, key="foo")
    rmock.request("POST", "https://test-dvla-api.com/thirdparty-access/v1/authenticate", json={"id-token": token})


def test_set_ssm_creds_saves_in_cache(ssm):
    param = SSMParameter(key="/foo", ssm_client=ssm)

    assert param._value is None

    param.set("new value")

    assert param._value == "new value"


def test_get_ssm_creds_returns_value_if_already_set(ssm):
    param = SSMParameter(key="/foo", ssm_client=ssm)

    param._value = "old value"

    ssm.put_parameter(Name="/foo", Value="new value", Type="SecureString")

    assert param.get() == "old value"


def test_get_ssm_creds_fetches_value_and_saves_in_cache_if_not_set(ssm):
    param = SSMParameter(key="/foo", ssm_client=ssm)
    ssm.put_parameter(Name="/foo", Value="bar", Type="SecureString")

    assert param._value is None

    assert param.get() == "bar"

    assert param._value == "bar"


def test_clear_ssm_creds_removes_locally_cached_value(ssm):
    param = SSMParameter(key="/foo", ssm_client=ssm)
    ssm.put_parameter(Name="/foo", Value="bar", Type="SecureString")

    param._value = "old value"

    param.clear()

    assert param._value is None


def test_get_ssm_creds(dvla_client, ssm):
    assert dvla_client.dvla_username.get() == "some username"
    assert dvla_client.dvla_password.get() == "some password"
    assert dvla_client.dvla_api_key.get() == "some api key"


def test_set_ssm_creds(dvla_client, ssm):
    dvla_client.dvla_username.set("some new username")
    dvla_client.dvla_password.set("some new password")
    dvla_client.dvla_api_key.set("some new api key")

    assert ssm.get_parameter(Name="/notify/api/dvla_username")["Parameter"]["Value"] == "some new username"
    assert ssm.get_parameter(Name="/notify/api/dvla_password")["Parameter"]["Value"] == "some new password"
    assert ssm.get_parameter(Name="/notify/api/dvla_api_key")["Parameter"]["Value"] == "some new api key"


def test_jwt_token_returns_jwt_if_set_and_not_expired_yet(dvla_client, rmock):
    curr_time = int(time.time())
    sample_token = jwt.encode(payload={"exp": curr_time + 3600}, key="foo")
    dvla_client._jwt_token = sample_token
    dvla_client._jwt_expires_at = curr_time + 3600

    assert dvla_client.jwt_token == sample_token


def test_jwt_token_calls_authenticate_if_not_set(dvla_client, rmock):
    assert dvla_client._jwt_token is None

    curr_time = int(time.time())
    one_hour_ahead = curr_time + 3600
    sample_token = jwt.encode(payload={"exp": one_hour_ahead}, key="foo")

    endpoint = "https://test-dvla-api.com/thirdparty-access/v1/authenticate"
    mock_authenticate = rmock.request("POST", endpoint, json={"id-token": sample_token}, status_code=200)

    assert dvla_client.jwt_token == sample_token
    assert dvla_client._jwt_expires_at == one_hour_ahead

    # despite accessing value twice, we only called authenticate once
    assert mock_authenticate.called_once
    assert rmock.last_request.json() == {"userName": "some username", "password": "some password"}
    assert rmock.last_request.headers["Content-Type"] == "application/json"


def test_jwt_token_calls_authenticate_if_expiry_time_passed(dvla_client, rmock):
    prev_token_expiry_time = time.time()
    sixty_one_seconds_before_expiry = prev_token_expiry_time - 61
    fifty_nine_seconds_before_expiry = prev_token_expiry_time - 59
    one_hour_later = fifty_nine_seconds_before_expiry + 3600

    old_token = jwt.encode(payload={"exp": prev_token_expiry_time}, key="foo")
    next_token = jwt.encode(payload={"exp": one_hour_later}, key="foo")

    dvla_client._jwt_token = jwt.encode(payload={"exp": prev_token_expiry_time}, key="foo")
    dvla_client._jwt_expires_at = prev_token_expiry_time

    with freezegun.freeze_time(datetime.fromtimestamp(sixty_one_seconds_before_expiry, tz=pytz.utc)):
        assert dvla_client.jwt_token == old_token

    endpoint = "https://test-dvla-api.com/thirdparty-access/v1/authenticate"
    mock_authenticate = rmock.request("POST", endpoint, json={"id-token": next_token}, status_code=200)

    with freezegun.freeze_time(datetime.fromtimestamp(fifty_nine_seconds_before_expiry, tz=pytz.utc)):
        assert dvla_client.jwt_token != old_token
        assert dvla_client._jwt_expires_at == one_hour_later

    assert mock_authenticate.called_once


def test_authenticate_raises_retryable_exception_if_credentials_are_invalid(dvla_client, rmock):
    assert dvla_client.dvla_password.get() == "some password"

    error_response = [{"status": 401, "title": "Authentication Failure", "detail": "Some detail"}]
    endpoint = "https://test-dvla-api.com/thirdparty-access/v1/authenticate"
    rmock.request("POST", endpoint, json=error_response, status_code=401)

    with pytest.raises(DvlaRetryableException) as exc:
        dvla_client.authenticate()

    assert dvla_client._jwt_token is None
    # clears down old credentials that are out of date
    assert dvla_client.dvla_password._value is None

    assert "Some detail" in str(exc.value)


@pytest.mark.parametrize(
    "status_code, exc_class",
    {
        400: DvlaException,
        429: DvlaThrottlingException,
        500: DvlaRetryableException,
    }.items(),
)
def test_authenticate_handles_generic_errors(dvla_client, rmock, status_code, exc_class):
    error_response = [{"status": status_code, "title": "Authentication Failure", "detail": "Some detail"}]
    endpoint = "https://test-dvla-api.com/thirdparty-access/v1/authenticate"
    rmock.request("POST", endpoint, json=error_response, status_code=status_code)

    with pytest.raises(exc_class):
        dvla_client.authenticate()

    assert dvla_client._jwt_token is None

    # old credentials are still stored as there's nothing to indicate they are invalid
    assert dvla_client.dvla_password.get() == "some password"


@pytest.mark.parametrize("_execution_number", range(100))
def test_generate_password_creates_passwords_that_meet_dvla_criteria(_execution_number):
    password = DVLAClient._generate_password()
    for character_set in (string.ascii_uppercase, string.ascii_lowercase, string.digits, string.punctuation):
        # assert the intersection of the character class, and the chars in the password is not empty to make sure
        # that all character classes are represented
        assert any(
            character in character_set for character in password
        ), f"{password} missing character from {character_set}"
    assert len(password) > 8


def test_change_password_calls_dvla(dvla_client, rmock, mocker):
    mocker.patch.object(dvla_client, "_generate_password", return_value="some new password")
    dvla_client.dvla_password._value = "some old password"

    endpoint = "https://test-dvla-api.com/thirdparty-access/v1/password"
    mock_change_password = rmock.request(
        "POST", endpoint, json={"message": "Password successfully changed."}, status_code=200
    )

    dvla_client.change_password()

    assert mock_change_password.called_once is True
    # assert we ignored the old password from cache and re-fetched from SSM
    assert rmock.last_request.json() == {
        "userName": "some username",
        "password": "some password",
        "newPassword": "some new password",
    }
    assert rmock.last_request.headers["Content-Type"] == "application/json"


def test_change_password_updates_ssm(dvla_client, rmock, mocker):
    mocker.patch.object(dvla_client, "_generate_password", return_value="some new password")
    mock_set_password = mocker.patch.object(dvla_client.dvla_password, "set")

    endpoint = "https://test-dvla-api.com/thirdparty-access/v1/password"
    rmock.request("POST", endpoint, json={"message": "Password successfully changed."}, status_code=200)

    dvla_client.change_password()

    mock_set_password.assert_called_once_with("some new password")


def test_change_password_does_not_update_ssm_if_dvla_throws_error(dvla_client, rmock, mocker):
    mocker.patch.object(dvla_client, "_generate_password", return_value="some new password")
    mock_set_password = mocker.patch.object(dvla_client.dvla_password, "set")
    assert dvla_client.dvla_password.get() == "some password"

    error_response = [{"status": 401, "title": "Authentication Failure", "detail": "Some detail"}]
    endpoint = "https://test-dvla-api.com/thirdparty-access/v1/password"
    rmock.request("POST", endpoint, json=error_response, status_code=401)

    with pytest.raises(DvlaNonRetryableException) as exc:
        dvla_client.change_password()

    # does not update ssm
    assert mock_set_password.called is False
    # clears down old credentials that are out of date
    assert dvla_client.dvla_password._value is None

    assert "Some detail" in str(exc.value)


@pytest.mark.parametrize(
    "status_code, exc_class",
    {
        400: DvlaException,
        429: DvlaThrottlingException,
        500: DvlaRetryableException,
    }.items(),
)
def test_change_password_handles_generic_errors(dvla_client, rmock, mocker, status_code, exc_class):
    mocker.patch.object(dvla_client, "_generate_password", return_value="some new password")
    mock_set_password = mocker.patch.object(dvla_client.dvla_password, "set")
    assert dvla_client.dvla_password.get() == "some password"

    error_response = [{"status": status_code, "title": "Authentication Failure", "detail": "Some detail"}]
    endpoint = "https://test-dvla-api.com/thirdparty-access/v1/password"
    rmock.request("POST", endpoint, json=error_response, status_code=status_code)

    with pytest.raises(exc_class):
        dvla_client.change_password()

    # does not update ssm
    assert mock_set_password.called is False
    # old credentials are still stored as there's nothing to indicate they are invalid
    assert dvla_client.dvla_password.get() == "some password"


def test_change_password_raises_if_other_process_holds_lock(dvla_client, rmock, mocker):
    mocker.patch("notifications_utils.clients.redis.redis_client.StubLock.__enter__", side_effect=LockError)
    mock_set_password = mocker.patch.object(dvla_client.dvla_password, "set")

    with pytest.raises(LockError):
        dvla_client.change_password()

    assert rmock.called is False
    assert mock_set_password.called is False


def test_change_api_key_calls_dvla(dvla_client, rmock):
    endpoint = "https://test-dvla-api.com/thirdparty-access/v1/new-api-key"
    mock_change_api_key = rmock.request("POST", endpoint, json={"newApiKey": "some new api_key"}, status_code=200)
    dvla_client._jwt_token = "some jwt token"
    dvla_client._jwt_expires_at = sys.maxsize
    dvla_client.dvla_api_key._value = "some old api key"

    dvla_client.change_api_key()

    assert mock_change_api_key.called_once is True
    # we ignored the old value in cache, and tried with the latest version from SSM
    assert rmock.last_request.headers["x-api-key"] == "some api key"
    assert rmock.last_request.headers["Authorization"] == "some jwt token"


def test_change_api_key_updates_ssm(dvla_client, rmock, mocker):
    mock_set_api_key = mocker.patch.object(dvla_client.dvla_api_key, "set")
    dvla_client._jwt_token = "some jwt token"
    dvla_client._jwt_expires_at = sys.maxsize

    endpoint = "https://test-dvla-api.com/thirdparty-access/v1/new-api-key"
    rmock.request("POST", endpoint, json={"newApiKey": "some new api_key"}, status_code=200)

    dvla_client.change_api_key()

    mock_set_api_key.assert_called_once_with("some new api_key")


def test_change_api_key_handles_401_authentication_error(dvla_client, rmock, mocker):
    mock_set_api_key = mocker.patch.object(dvla_client.dvla_api_key, "set")
    dvla_client._jwt_token = "some jwt token"
    dvla_client._jwt_expires_at = sys.maxsize
    assert dvla_client.dvla_api_key.get() == "some api key"

    error_response = [{"status": 401, "title": "Authentication Failure", "detail": "Some detail"}]
    endpoint = "https://test-dvla-api.com/thirdparty-access/v1/new-api-key"
    rmock.request("POST", endpoint, json=error_response, status_code=401)

    with pytest.raises(DvlaNonRetryableException) as exc:
        dvla_client.change_api_key()

    # does not update ssm
    assert mock_set_api_key.called is False
    # clears down old credentials that are out of date
    assert dvla_client.dvla_api_key._value is None

    assert "Some detail" in str(exc.value)


@pytest.mark.parametrize(
    "status_code, exc_class",
    {
        400: DvlaException,
        429: DvlaThrottlingException,
        500: DvlaRetryableException,
    }.items(),
)
def test_change_api_key_handles_generic_errors(dvla_client, rmock, mocker, status_code, exc_class):
    mock_set_api_key = mocker.patch.object(dvla_client.dvla_api_key, "set")
    dvla_client._jwt_token = "some jwt token"
    dvla_client._jwt_expires_at = sys.maxsize
    assert dvla_client.dvla_api_key.get() == "some api key"

    error_response = [{"status": status_code, "title": "Authentication Failure", "detail": "Some detail"}]
    endpoint = "https://test-dvla-api.com/thirdparty-access/v1/new-api-key"
    rmock.request("POST", endpoint, json=error_response, status_code=status_code)

    with pytest.raises(exc_class):
        dvla_client.change_api_key()

    # does not update ssm
    assert mock_set_api_key.called is False
    # old credentials are still stored as there's nothing to indicate they are invalid
    assert dvla_client.dvla_api_key.get() == "some api key"


def test_change_api_key_raises_if_other_process_holds_lock(dvla_client, rmock, mocker):
    mocker.patch("notifications_utils.clients.redis.redis_client.StubLock.__enter__", side_effect=LockError)
    mock_set_api_key = mocker.patch.object(dvla_client.dvla_api_key, "set")

    with pytest.raises(LockError):
        dvla_client.change_api_key()

    assert rmock.called is False
    assert mock_set_api_key.called is False


def test_format_create_print_job_json_builds_json_body_to_create_print_job(dvla_client):
    formatted_json = dvla_client._format_create_print_job_json(
        notification_id="my_notification_id",
        reference="ABCDEFGHIJKL",
        address=PostalAddress("A. User\nThe road\nCity\nSW1 1AA"),
        postage="second",
        service_id="my_service_id",
        organisation_id="my_organisation_id",
        pdf_file=b"pdf_content",
    )

    assert formatted_json == {
        "id": "my_notification_id",
        "standardParams": {
            "jobType": "NOTIFY",
            "templateReference": "NOTIFY",
            "businessIdentifier": "ABCDEFGHIJKL",
            "recipientName": "A. User",
            "address": {"unstructuredAddress": {"line1": "The road", "line2": "City", "postcode": "SW1 1AA"}},
        },
        "customParams": [
            {"key": "pdfContent", "value": "cGRmX2NvbnRlbnQ="},
            {"key": "organisationIdentifier", "value": "my_organisation_id"},
            {"key": "serviceIdentifier", "value": "my_service_id"},
        ],
    }


def test_format_create_print_job_json_adds_despatchMethod_key_for_first_class_post(dvla_client):
    formatted_json = dvla_client._format_create_print_job_json(
        notification_id="my_notification_id",
        reference="ABCDEFGHIJKL",
        address=PostalAddress("A. User\nThe road\nCity\nSW1 1AA"),
        postage="first",
        service_id="my_service_id",
        organisation_id="my_organisation_id",
        pdf_file=b"pdf_content",
    )

    assert formatted_json["standardParams"]["despatchMethod"] == "FIRST"


@pytest.mark.parametrize(
    "address, recipient, unstructured_address",
    [
        (PostalAddress("The user\nThe road\nSW1 1AA"), "The user", {"line1": "The road", "postcode": "SW1 1AA"}),
        (
            PostalAddress("The user\nHouse no.\nMy Street\nSW1 1AA"),
            "The user",
            {"line1": "House no.", "line2": "My Street", "postcode": "SW1 1AA"},
        ),
        (
            PostalAddress("The user\n1\n2\n3\n4\n5\nSW1 1AA"),
            "The user",
            {"line1": "1", "line2": "2", "line3": "3", "line4": "4", "line5": "5", "postcode": "SW1 1AA"},
        ),
        (
            PostalAddress("The user\n1\n" + ("2" * 50) + "\n3\n4\n5\nSW1 1AA"),
            "The user",
            {"line1": "1", "line2": "2" * 45, "line3": "3", "line4": "4", "line5": "5", "postcode": "SW1 1AA"},
        ),
        (
            PostalAddress("The user\n1\n2\n3\n4\n5\nPostcode over ten characters"),
            "The user",
            {"line1": "1", "line2": "2", "line3": "3", "line4": "4", "line5": "5", "postcode": "Postcode o"},
        ),
    ],
)
def test_format_create_print_job_json_formats_address_lines(dvla_client, address, recipient, unstructured_address):
    formatted_json = dvla_client._format_create_print_job_json(
        notification_id="my_notification_id",
        reference="ABCDEFGHIJKL",
        address=address,
        postage="first",
        service_id="my_service_id",
        organisation_id="my_organisation_id",
        pdf_file=b"pdf_content",
    )

    assert formatted_json["standardParams"]["recipientName"] == recipient
    assert formatted_json["standardParams"]["address"]["unstructuredAddress"] == unstructured_address


def test_format_create_print_job_json_formats_international_address_lines(dvla_client):
    address = PostalAddress("The user\nThe road\nSW1 1AA\nFrance", allow_international_letters=True)
    expected_address = {"line1": "The road", "line2": "SW1 1AA", "country": "France"}

    formatted_json = dvla_client._format_create_print_job_json(
        notification_id="my_notification_id",
        reference="ABCDEFGHIJKL",
        address=address,
        postage="europe",
        service_id="my_service_id",
        organisation_id="my_organisation_id",
        pdf_file=b"pdf_content",
    )

    assert formatted_json["standardParams"]["recipientName"] == "The user"
    assert formatted_json["standardParams"]["address"]["internationalAddress"] == expected_address


def test_send_domestic_letter(dvla_client, dvla_authenticate, rmock):
    print_mock = rmock.post(
        f"{current_app.config['DVLA_API_BASE_URL']}/print-request/v1/print/jobs",
        json={"id": "noti_id"},
        status_code=202,
    )

    response = dvla_client.send_letter(
        notification_id="noti_id",
        reference="ABCDEFGHIJKL",
        address=PostalAddress("recipient\ncity\npostcode"),
        postage="second",
        service_id="service_id",
        organisation_id="org_id",
        pdf_file=b"pdf",
    )

    assert response == {"id": "noti_id"}

    assert print_mock.last_request.json() == {
        "id": "noti_id",
        "standardParams": {
            "jobType": "NOTIFY",
            "templateReference": "NOTIFY",
            "businessIdentifier": "ABCDEFGHIJKL",
            "recipientName": "recipient",
            "address": {"unstructuredAddress": {"line1": "city", "postcode": "postcode"}},
        },
        "customParams": [
            {"key": "pdfContent", "value": "cGRm"},
            {"key": "organisationIdentifier", "value": "org_id"},
            {"key": "serviceIdentifier", "value": "service_id"},
        ],
    }

    request_headers = print_mock.last_request.headers

    assert request_headers["Accept"] == "application/json"
    assert request_headers["Content-Type"] == "application/json"
    assert request_headers["X-API-Key"] == "some api key"
    assert request_headers["Authorization"]


@pytest.mark.parametrize(
    "postage, despatch_method", (("europe", "INTERNATIONAL_EU"), ("rest-of-world", "INTERNATIONAL_ROW"))
)
def test_send_international_letter(dvla_client, dvla_authenticate, postage, despatch_method, rmock):
    print_mock = rmock.post(
        f"{current_app.config['DVLA_API_BASE_URL']}/print-request/v1/print/jobs",
        json={"id": "noti_id"},
        status_code=202,
    )

    response = dvla_client.send_letter(
        notification_id="noti_id",
        reference="ABCDEFGHIJKL",
        address=PostalAddress("recipient\nline1\nline2\ncountry"),
        postage=postage,
        service_id="service_id",
        organisation_id="org_id",
        pdf_file=b"pdf",
    )

    assert response == {"id": "noti_id"}

    assert print_mock.last_request.json() == {
        "id": "noti_id",
        "standardParams": {
            "jobType": "NOTIFY",
            "templateReference": "NOTIFY",
            "businessIdentifier": "ABCDEFGHIJKL",
            "recipientName": "recipient",
            "address": {"internationalAddress": {"line1": "line1", "line2": "line2", "country": "country"}},
            "despatchMethod": despatch_method,
        },
        "customParams": [
            {"key": "pdfContent", "value": "cGRm"},
            {"key": "organisationIdentifier", "value": "org_id"},
            {"key": "serviceIdentifier", "value": "service_id"},
        ],
    }


def test_send_bfpo_letter(dvla_client, dvla_authenticate, rmock):
    print_mock = rmock.post(
        f"{current_app.config['DVLA_API_BASE_URL']}/print-request/v1/print/jobs",
        json={"id": "noti_id"},
        status_code=202,
    )

    response = dvla_client.send_letter(
        notification_id="noti_id",
        reference="ABCDEFGHIJKL",
        address=PostalAddress("recipient\nbfpo\nbfpo1234\nbf11aa"),
        postage="second",
        service_id="service_id",
        organisation_id="org_id",
        pdf_file=b"pdf",
    )

    assert response == {"id": "noti_id"}

    assert print_mock.last_request.json() == {
        "id": "noti_id",
        "standardParams": {
            "jobType": "NOTIFY",
            "templateReference": "NOTIFY",
            "businessIdentifier": "ABCDEFGHIJKL",
            "recipientName": "recipient",
            "address": {"bfpoAddress": {"line1": "recipient", "postcode": "BF1 1AA", "bfpoNumber": 1234}},
        },
        "customParams": [
            {"key": "pdfContent", "value": "cGRm"},
            {"key": "organisationIdentifier", "value": "org_id"},
            {"key": "serviceIdentifier", "value": "service_id"},
        ],
    }


def test_send_letter_when_bad_request_error_is_raised(dvla_authenticate, dvla_client, rmock):
    rmock.post(
        f"{current_app.config['DVLA_API_BASE_URL']}/print-request/v1/print/jobs",
        json={
            "errors": [
                {
                    "status": "400 BAD_REQUEST",
                    "code": "NotEmpty",
                    "title": "standardParams.jobType",
                    "detail": "Job type field must not be empty.",
                },
                {
                    "status": "400 BAD_REQUEST",
                    "code": "NotEmpty",
                    "title": "standardParams.templateReference",
                    "detail": "Template reference field must not be empty.",
                },
            ]
        },
        status_code=400,
    )

    with pytest.raises(DvlaNonRetryableException) as exc:
        dvla_client.send_letter(
            notification_id="1",
            reference="ABCDEFGHIJKL",
            address=PostalAddress("line\nline2\npostcode"),
            postage="second",
            service_id="s_id",
            organisation_id="org_id",
            pdf_file=b"pdf",
        )

    assert "Job type field must not be empty." in str(exc.value)


@pytest.mark.parametrize("status_code", [401, 403])
def test_send_letter_when_auth_error_is_raised(dvla_authenticate, dvla_client, rmock, status_code):
    rmock.post(
        f"{current_app.config['DVLA_API_BASE_URL']}/print-request/v1/print/jobs",
        json={
            "errors": [
                {
                    "status": f"{status_code}",
                    "code": "Unauthorized",
                    "detail": "API Key or JWT is either not provided, expired or invalid",
                }
            ]
        },
        status_code=status_code,
    )
    assert dvla_client.dvla_api_key.get() == "some api key"

    with pytest.raises(DvlaUnauthorisedRequestException) as exc:
        dvla_client.send_letter(
            notification_id="noti_id",
            reference="ABCDEFGHIJKL",
            address=PostalAddress("line\nline2\npostcode"),
            postage="second",
            service_id="s_id",
            organisation_id="org_id",
            pdf_file=b"pdf",
        )

    # make sure we clear down the api key
    assert dvla_client.dvla_api_key._value is None

    assert "API Key or JWT is either not provided, expired or invalid" in str(exc.value)


def test_send_letter_when_conflict_error_is_raised(dvla_authenticate, dvla_client, rmock):
    rmock.post(
        f"{current_app.config['DVLA_API_BASE_URL']}/print-request/v1/print/jobs",
        json={
            "errors": [
                {
                    "status": "409 CONFLICT",
                    "code": "11",
                    "title": "Print job cannot be created",
                    "detail": (
                        "The supplied identifier 1 conflicts with another print job. "
                        "Please supply a unique identifier."
                    ),
                }
            ]
        },
        status_code=409,
    )

    with pytest.raises(DvlaDuplicatePrintRequestException) as exc:
        dvla_client.send_letter(
            notification_id="1",
            reference="ABCDEFGHIJKL",
            address=PostalAddress("line\nline2\npostcode"),
            postage="second",
            service_id="s_id",
            organisation_id="org_id",
            pdf_file=b"pdf",
        )

    assert "The supplied identifier 1 conflicts with another print job" in str(exc.value)


def test_send_letter_when_throttling_error_is_raised(dvla_authenticate, dvla_client, rmock):
    rmock.post(
        f"{current_app.config['DVLA_API_BASE_URL']}/print-request/v1/print/jobs",
        json={
            "errors": [
                {
                    "status": "429",
                    "title": "Too Many Requests",
                    "detail": "Too Many Requests",
                }
            ]
        },
        status_code=429,
    )

    with pytest.raises(DvlaThrottlingException):
        dvla_client.send_letter(
            notification_id="1",
            reference="ABCDEFGHIJKL",
            address=PostalAddress("line\nline2\npostcode"),
            postage="second",
            service_id="s_id",
            organisation_id="org_id",
            pdf_file=b"pdf",
        )


def test_send_letter_when_5xx_status_code_is_returned(dvla_authenticate, dvla_client, rmock):
    url = f"{current_app.config['DVLA_API_BASE_URL']}/print-request/v1/print/jobs"
    rmock.post(url, status_code=500)

    with pytest.raises(DvlaRetryableException) as exc:
        dvla_client.send_letter(
            notification_id="1",
            reference="ABCDEFGHIJKL",
            address=PostalAddress("line\nline2\npostcode"),
            postage="second",
            service_id="s_id",
            organisation_id="org_id",
            pdf_file=b"pdf",
        )
    assert str(exc.value) == f"Received 500 from {url}"


@pytest.mark.parametrize(
    "exc_type", [ConnectionResetError, requests.exceptions.SSLError, requests.exceptions.ConnectTimeout]
)
def test_send_letter_when_connection_error_is_returned(dvla_authenticate, dvla_client, rmock, exc_type):
    rmock.post(f"{current_app.config['DVLA_API_BASE_URL']}/print-request/v1/print/jobs", exc=exc_type)

    with pytest.raises(DvlaRetryableException):
        dvla_client.send_letter(
            notification_id="1",
            reference="ABCDEFGHIJKL",
            address=PostalAddress("line\nline2\npostcode"),
            postage="second",
            service_id="s_id",
            organisation_id="org_id",
            pdf_file=b"pdf",
        )


def test_send_letter_when_unknown_exception_is_raised(dvla_authenticate, dvla_client, rmock):
    rmock.post(
        f"{current_app.config['DVLA_API_BASE_URL']}/print-request/v1/print/jobs",
        status_code=418,
    )

    with pytest.raises(DvlaNonRetryableException):
        dvla_client.send_letter(
            notification_id="1",
            reference="ABCDEFGHIJKL",
            address=PostalAddress("line\nline2\npostcode"),
            postage="second",
            service_id="s_id",
            organisation_id="org_id",
            pdf_file=b"pdf",
        )


class TestDVLAApiClientRestrictedCiphers:
    """A test suite that actually spins up an HTTP server with TLS support.

    This will let us prove that we are restricting the available TLS ciphers and won't connect if
    we're unable to negotiate one of the ciphers we want."""

    @pytest.fixture(scope="session")
    def ca(self):
        return trustme.CA()

    @pytest.fixture(scope="session")
    def httpserver_listen_address(self):
        hostname = "localhost"

        sock = socket.socket()
        sock.bind(("localhost", 0))
        port = sock.getsockname()[1]
        sock.close()

        return hostname, port

    @pytest.fixture(scope="session")
    def server_base_url(self, httpserver_listen_address):
        hostname, port = httpserver_listen_address
        return f"https://{hostname}:{port}/"

    @pytest.fixture(scope="session")
    def cipherlist(self):
        ctx = ssl.SSLContext()
        all_ciphers = [c["name"] for c in ctx.get_ciphers()]
        allowlist = all_ciphers[:-1]  # All but the last cipher
        blocklist = all_ciphers[-1:]  # The last cipher

        ctx.set_ciphers(":".join(allowlist))
        assert blocklist[0] not in ctx.get_ciphers(), "Excluded cipher is still allowed"

        CipherList = namedtuple("CipherList", ("allowlist", "blocklist"))
        return CipherList(
            allowlist,
            blocklist,
        )

    @pytest.fixture(scope="session")
    def allow_ctx(self, cipherlist):
        ctx = ssl.SSLContext()
        ctx.set_ciphers(":".join(cipherlist.allowlist))

        # Manually disable TLS v 1.3. Those ciphers are automatically allowed even if we don't include
        # any in `ctx.set_ciphers`. If we don't disable this for the server, then regardless of whether we define
        # disjunct cipher suites on each side, both will accept and negotiate TLSv1_3 and still connect.
        ctx.options |= ssl.OP_NO_TLSv1_3

        return ctx

    @pytest.fixture(scope="session")
    def httpserver_ssl_context(self, ca, allow_ctx):
        localhost_cert = ca.issue_cert("localhost")
        ca.configure_trust(allow_ctx)
        localhost_cert.configure_cert(allow_ctx)

        def default_context():
            return allow_ctx

        before = ssl._create_default_https_context
        ssl._create_default_https_context = default_context
        try:
            yield allow_ctx
        finally:
            ssl._create_default_https_context = before

    @pytest.fixture
    def fake_app(self, mocker, server_base_url):
        application = mocker.Mock()
        application.config = {
            "DVLA_API_BASE_URL": server_base_url,
            "DVLA_API_TLS_CIPHERS": None,
            "AWS_REGION": "somewhere",
        }
        return application

    def test_valid_default_connection(
        self, mocker, httpserver, httpserver_listen_address, httpserver_ssl_context, ca, server_base_url, fake_app
    ):
        httpserver.expect_request(
            "/test",
            method="GET",
        ).respond_with_data("OK")

        dvla_client = DVLAClient()
        dvla_client.init_app(
            fake_app,
            statsd_client=mocker.Mock(),
        )

        with ca.cert_pem.tempfile() as ca_temp_path:
            response = dvla_client.session.get(
                f"{server_base_url}/test",
                verify=ca_temp_path,
            )

        assert response.text == "OK"

    def test_invalid_ciphers(self, mocker, server_base_url, fake_app):
        dvla_client = DVLAClient()

        with pytest.raises(ssl.SSLError) as e:
            fake_app.config["DVLA_API_TLS_CIPHERS"] = "not-a-valid-cipher"
            dvla_client.init_app(fake_app, statsd_client=mocker.Mock())

        assert "No cipher can be selected." in e.value.args

    def test_accept_matching_cipher(
        self,
        mocker,
        httpserver,
        httpserver_listen_address,
        httpserver_ssl_context,
        ca,
        cipherlist,
        server_base_url,
        fake_app,
    ):
        fake_app.config["DVLA_API_TLS_CIPHERS"] = ":".join(cipherlist.allowlist)
        dvla_client = DVLAClient()
        dvla_client.init_app(
            fake_app,
            statsd_client=mocker.Mock(),
        )

        httpserver.expect_request(
            "/test",
            method="GET",
        ).respond_with_data("OK")

        with ca.cert_pem.tempfile() as ca_temp_path:
            response = dvla_client.session.get(
                f"{server_base_url}/test",
                verify=ca_temp_path,
            )

        assert response.text == "OK"

    def test_reject_cipher_not_accepted_by_server(
        self,
        mocker,
        httpserver,
        httpserver_listen_address,
        httpserver_ssl_context,
        ca,
        cipherlist,
        server_base_url,
        fake_app,
    ):
        fake_app.config["DVLA_API_TLS_CIPHERS"] = ":".join(cipherlist.blocklist)
        dvla_client = DVLAClient()
        dvla_client.init_app(
            fake_app,
            statsd_client=mocker.Mock(),
        )

        httpserver.expect_request(
            "/test",
            method="GET",
        ).respond_with_data("OK")

        with pytest.raises(requests.exceptions.SSLError) as e:
            with ca.cert_pem.tempfile() as ca_temp_path:
                dvla_client.session.get(
                    f"{server_base_url}/test",
                    verify=ca_temp_path,
                )

        assert "alert handshake failure" in str(e.value)
