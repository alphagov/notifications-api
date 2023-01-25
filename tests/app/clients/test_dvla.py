import time
from datetime import datetime
from unittest.mock import Mock

import boto3
import freezegun
import jwt
import pytest
from moto import mock_ssm

from app.clients.letter.dvla import DVLAClient


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
def dvla_client(ssm):
    dvla_client = DVLAClient()
    dvla_client.init_app(region="eu-west-1", statsd_client=Mock())
    yield dvla_client


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


def test_jwt_token_returns_jwt_if_set_and_not_expired_yet(client, dvla_client, rmock):
    curr_time = int(time.time())
    sample_token = jwt.encode(payload={"exp": curr_time + 3600}, key="foo")
    dvla_client._jwt_token = sample_token
    dvla_client._jwt_expires_at = curr_time + 3600

    assert dvla_client.jwt_token == sample_token


def test_jwt_token_calls_authenticate_if_not_set(client, dvla_client, rmock):
    assert dvla_client._jwt_token is None

    curr_time = int(time.time())
    sample_token = jwt.encode(payload={"exp": curr_time}, key="foo")

    endpoint = "https://test-dvla-api.com/thirdparty-access/v1/authenticate"
    mock_authenticate = rmock.request("POST", endpoint, json={"id-token": sample_token}, status_code=200)

    assert dvla_client.jwt_token == sample_token
    assert dvla_client._jwt_expires_at == int(time.time())

    # despite accessing value twice, we only called authenticate once
    assert mock_authenticate.called_once
    assert rmock.last_request.json() == {"userName": "some username", "password": "some password"}
    assert rmock.last_request.headers["Content-Type"] == "application/json"


def test_jwt_token_calls_authenticate_if_expiry_time_passed(client, dvla_client, rmock):
    prev_token_expiry_time = time.time()
    one_second_later = prev_token_expiry_time + 1
    one_hour_later = one_second_later + 3600

    old_token = jwt.encode(payload={"exp": prev_token_expiry_time}, key="foo")
    next_token = jwt.encode(payload={"exp": one_hour_later}, key="foo")

    dvla_client._jwt_token = jwt.encode(payload={"exp": prev_token_expiry_time}, key="foo")
    dvla_client._jwt_expires_at = prev_token_expiry_time

    endpoint = "https://test-dvla-api.com/thirdparty-access/v1/authenticate"
    mock_authenticate = rmock.request("POST", endpoint, json={"id-token": next_token}, status_code=200)

    with freezegun.freeze_time(datetime.fromtimestamp(one_second_later)):
        assert dvla_client.jwt_token != old_token
        assert dvla_client._jwt_expires_at == one_hour_later

    assert mock_authenticate.called_once
