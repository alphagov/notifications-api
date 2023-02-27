import string
import sys
import time
from datetime import datetime
from unittest.mock import Mock

import boto3
import freezegun
import jwt
import pytest
from flask import current_app
from moto import mock_ssm
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
def dvla_client(client, ssm):
    dvla_client = DVLAClient()
    dvla_client.init_app(region="eu-west-1", statsd_client=Mock())
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

    with freezegun.freeze_time(datetime.fromtimestamp(sixty_one_seconds_before_expiry)):
        assert dvla_client.jwt_token == old_token

    endpoint = "https://test-dvla-api.com/thirdparty-access/v1/authenticate"
    mock_authenticate = rmock.request("POST", endpoint, json={"id-token": next_token}, status_code=200)

    with freezegun.freeze_time(datetime.fromtimestamp(fifty_nine_seconds_before_expiry)):
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
        address_lines=["A. User", "The road", "City", "SW1 1AA"],
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
        address_lines=["A. User", "The road", "City", "SW1 1AA"],
        postage="first",
        service_id="my_service_id",
        organisation_id="my_organisation_id",
        pdf_file=b"pdf_content",
    )

    assert formatted_json["standardParams"]["despatchMethod"] == "FIRST"


@pytest.mark.parametrize(
    "address_lines, recipient, unstructured_address",
    [
        (["The user", "The road", "SW1 1AA"], "The user", {"line1": "The road", "postcode": "SW1 1AA"}),
        (
            ["The user", "House no.", "My Street", "SW1 1AA"],
            "The user",
            {"line1": "House no.", "line2": "My Street", "postcode": "SW1 1AA"},
        ),
        (
            ["The user", "1", "2", "3", "4", "5", "SW1 1AA"],
            "The user",
            {"line1": "1", "line2": "2", "line3": "3", "line4": "4", "line5": "5", "postcode": "SW1 1AA"},
        ),
    ],
)
def test_format_create_print_job_json_formats_address_lines(
    dvla_client, address_lines, recipient, unstructured_address
):
    formatted_json = dvla_client._format_create_print_job_json(
        notification_id="my_notification_id",
        reference="ABCDEFGHIJKL",
        address_lines=address_lines,
        postage="first",
        service_id="my_service_id",
        organisation_id="my_organisation_id",
        pdf_file=b"pdf_content",
    )

    assert formatted_json["standardParams"]["recipientName"] == recipient
    assert formatted_json["standardParams"]["address"]["unstructuredAddress"] == unstructured_address


def test_send_domestic_letter(dvla_client, dvla_authenticate, rmock):
    print_mock = rmock.post(
        f"{current_app.config['DVLA_API_BASE_URL']}/print-request/v1/print/jobs",
        json={"id": "noti_id"},
        status_code=202,
    )

    response = dvla_client.send_letter(
        notification_id="noti_id",
        reference="ABCDEFGHIJKL",
        address=["recipient", "city", "postcode"],
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
        address=["recipient", "line1", "line2", "country"],
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
            address=["line1", "line2", "postcode"],
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
            address=["line1", "line2", "postcode"],
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
            address=["line1", "line2", "postcode"],
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
            address=["line1", "line2", "postcode"],
            postage="second",
            service_id="s_id",
            organisation_id="org_id",
            pdf_file=b"pdf",
        )


def test_send_letter_when_5xx_status_code_is_returned(dvla_authenticate, dvla_client, rmock):
    rmock.post(
        f"{current_app.config['DVLA_API_BASE_URL']}/print-request/v1/print/jobs",
        status_code=500,
    )

    with pytest.raises(DvlaRetryableException):
        dvla_client.send_letter(
            notification_id="1",
            reference="ABCDEFGHIJKL",
            address=["line1", "line2", "postcode"],
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
            address=["line1", "line2", "postcode"],
            postage="second",
            service_id="s_id",
            organisation_id="org_id",
            pdf_file=b"pdf",
        )
