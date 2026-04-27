import os
from datetime import datetime, timedelta

import boto3
import pytest
from moto import mock_aws

from app import db
from app.functional_tests_fixtures import _create_db_objects, _create_user, apply_fixtures
from app.models import Service, Template
from tests.conftest import set_config_values


def test_create_db_objects_sets_db_up(notify_api, notify_service):
    functional_test_password = "fake password"
    request_bin_api_token = "test_request_bin_token"
    environment = "dev-env"
    test_email_username = "notify-tests-preview"
    email_domain = "digital.cabinet-office.gov.uk"
    function_tests_govuk_key_name = "govuk_notify"
    function_tests_live_key_name = "functional_tests_service_live_key"
    function_tests_test_key_name = "functional_tests_service_test_key"
    govuk_service_id = str(notify_service.id)

    # repeat twice to test idempotence
    variables = []

    for _ in range(2):
        with set_config_values(
            notify_api,
            {
                "MMG_INBOUND_SMS_USERNAME": ["test_mmg_username"],
                "MMG_INBOUND_SMS_AUTH": ["test_mmg_password"],
                "INTERNAL_CLIENT_API_KEYS": {"notify-functional-tests": ["functional-tests-secret-key"]},
                "ADMIN_BASE_URL": "http://localhost:6012",
                "API_HOST_NAME": "http://localhost:6011",
            },
        ):
            variables.append(
                _create_db_objects(
                    functional_test_password,
                    request_bin_api_token,
                    environment,
                    test_email_username,
                    email_domain,
                    function_tests_govuk_key_name,
                    function_tests_live_key_name,
                    function_tests_test_key_name,
                    govuk_service_id,
                    "Functional Tests Org",
                    "07700900500",
                )
            )
            db.session.commit()

    assert variables[0] == variables[1], "results are not idempotent"

    functional_vars, performance_vars = variables[0]

    assert functional_vars["FUNCTIONAL_TESTS_API_HOST"] == "http://localhost:6011"
    assert functional_vars["FUNCTIONAL_TESTS_ADMIN_HOST"] == "http://localhost:6012"
    assert functional_vars["ENVIRONMENT"] == "dev-env"
    assert functional_vars["FUNCTIONAL_TEST_EMAIL"] == "notify-tests-preview+dev-env@digital.cabinet-office.gov.uk"
    assert "FUNCTIONAL_TEST_PASSWORD" in functional_vars
    assert functional_vars["TEST_NUMBER"] == "07700900001"
    assert functional_vars["NOTIFY_SERVICE_API_KEY"].startswith("govuk_notify-")
    assert (
        functional_vars["FUNCTIONAL_TESTS_SERVICE_EMAIL"]
        == "notify-tests-preview+dev-env-admin-tests@digital.cabinet-office.gov.uk"
    )
    assert (
        functional_vars["FUNCTIONAL_TESTS_SERVICE_EMAIL_AUTH_ACCOUNT"]
        == "notify-tests-preview+dev-env-email-auth@digital.cabinet-office.gov.uk"
    )
    assert "FUNCTIONAL_TESTS_SERVICE_EMAIL_PASSWORD" in functional_vars
    assert functional_vars["FUNCTIONAL_TESTS_SERVICE_NUMBER"] == "07700900501"
    assert "FUNCTIONAL_TESTS_SERVICE_ID" in functional_vars
    assert functional_vars["FUNCTIONAL_TESTS_SERVICE_NAME"] == "Functional Tests"
    assert "FUNCTIONAL_TESTS_ORGANISATION_ID" in functional_vars
    assert functional_vars["FUNCTIONAL_TESTS_SERVICE_API_KEY"].startswith("functional_tests_service_live_key-")
    assert functional_vars["FUNCTIONAL_TESTS_SERVICE_API_TEST_KEY"].startswith("functional_tests_service_test_key-")
    assert performance_vars["PERFORMANCE_TESTS_API_HOST"] == "http://localhost:6011"
    assert performance_vars["PERFORMANCE_TESTS_SERVICE_API_KEY"].startswith("performance_tests_service_live_key-")
    assert functional_vars["FUNCTIONAL_TESTS_API_AUTH_SECRET"] == "functional-tests-secret-key"
    assert (
        functional_vars["FUNCTIONAL_TESTS_SERVICE_EMAIL_REPLY_TO"]
        == "notify-tests-preview+dev-env-reply-to@digital.cabinet-office.gov.uk"
    )
    assert (
        functional_vars["FUNCTIONAL_TESTS_SERVICE_EMAIL_REPLY_TO_2"]
        == "notify-tests-preview+dev-env-reply-to+2@digital.cabinet-office.gov.uk"
    )
    assert (
        functional_vars["FUNCTIONAL_TESTS_SERVICE_EMAIL_REPLY_TO_3"]
        == "notify-tests-preview+dev-env-reply-to+3@digital.cabinet-office.gov.uk"
    )
    assert functional_vars["FUNCTIONAL_TESTS_SERVICE_INBOUND_NUMBER"] == "07700900500"
    assert "FUNCTIONAL_TEST_SMS_TEMPLATE_ID" in functional_vars
    assert "FUNCTIONAL_TEST_EMAIL_TEMPLATE_ID" in functional_vars
    assert "FUNCTIONAL_TEST_LETTER_TEMPLATE_ID" in functional_vars
    assert "PERFORMANCE_TEST_SMS_TEMPLATE_ID" in performance_vars
    assert "PERFORMANCE_TEST_EMAIL_TEMPLATE_ID" in performance_vars
    assert "PERFORMANCE_TEST_EMAIL_WITH_FILE_TEMPLATE_ID" in performance_vars
    assert "PERFORMANCE_TEST_LETTER_TEMPLATE_ID" in performance_vars
    assert "FUNCTIONAL_TEST_SMS_NO_PLACEHOLDER_TEMPLATE_ID" in functional_vars
    assert "FUNCTIONAL_TEST_EMAIL_NO_PLACEHOLDER_TEMPLATE_ID" in functional_vars
    assert functional_vars["MMG_INBOUND_SMS_USERNAME"] == "test_mmg_username"
    assert functional_vars["MMG_INBOUND_SMS_AUTH"] == "test_mmg_password"
    assert functional_vars["REQUEST_BIN_API_TOKEN"] == "test_request_bin_token"

    for value in {**functional_vars, **performance_vars}.values():
        assert "'" not in str(value), "value cannot contain single quote"


def test_create_user_revalidates_email():
    test_user = _create_user("test_user", "test@example.com", "passw@rd", auth_type="email_auth")
    test_user.email_access_validated_at = datetime.utcnow() - timedelta(days=365)
    db.session.commit()
    test_user = _create_user("test_user", "test@example.com", "passw@rd", auth_type="email_auth")
    assert (datetime.utcnow() - test_user.email_access_validated_at).total_seconds() < 60


def test_create_db_objects_creates_dedicated_performance_service_with_limits_and_templates(notify_api, notify_service):
    functional_test_password = "fake password"
    request_bin_api_token = "test_request_bin_token"
    environment = "dev-env"
    test_email_username = "notify-tests-preview"
    email_domain = "digital.cabinet-office.gov.uk"
    function_tests_govuk_key_name = "govuk_notify"
    function_tests_live_key_name = "functional_tests_service_live_key"
    function_tests_test_key_name = "functional_tests_service_test_key"
    govuk_service_id = str(notify_service.id)

    with set_config_values(
        notify_api,
        {
            "MMG_INBOUND_SMS_USERNAME": ["test_mmg_username"],
            "MMG_INBOUND_SMS_AUTH": ["test_mmg_password"],
            "INTERNAL_CLIENT_API_KEYS": {"notify-functional-tests": ["functional-tests-secret-key"]},
            "ADMIN_BASE_URL": "http://localhost:6012",
            "API_HOST_NAME": "http://localhost:6011",
        },
    ):
        functional_vars, performance_vars = _create_db_objects(
            functional_test_password,
            request_bin_api_token,
            environment,
            test_email_username,
            email_domain,
            function_tests_govuk_key_name,
            function_tests_live_key_name,
            function_tests_test_key_name,
            govuk_service_id,
            "Functional Tests Org",
            "07700900500",
        )
        db.session.commit()

    functional_service = Service.query.filter_by(_name="Functional Tests").one()
    performance_service = Service.query.filter_by(_name="Performance Tests").one()

    assert performance_service.id != functional_service.id
    assert performance_service.rate_limit == 12000000
    assert performance_service.sms_message_limit == 5000000000
    assert performance_service.email_message_limit == 5000000000
    assert performance_service.letter_message_limit == 5000000000

    for template_id_key in (
        "PERFORMANCE_TEST_SMS_TEMPLATE_ID",
        "PERFORMANCE_TEST_EMAIL_TEMPLATE_ID",
        "PERFORMANCE_TEST_EMAIL_WITH_FILE_TEMPLATE_ID",
        "PERFORMANCE_TEST_LETTER_TEMPLATE_ID",
    ):
        template = db.session.get(Template, performance_vars[template_id_key])
        assert template is not None
        assert template.service_id == performance_service.id


@mock_aws
def test_function_test_fixtures_uploads_to_ssm(notify_api, os_environ, mocker):
    mocker.patch(
        "app.functional_tests_fixtures._create_db_objects",
        return_value=({"FOO": "BAR", "PASSWORD": "super-secret", "TOKEN": "abc123"}, {}),
    )

    os.environ["SSM_UPLOAD_PATH"] = "/test/ssm/environment"
    # AWS are changing from AWS_DEFAULT_REGION to AWS_REGION for v2 clients. Set both for now.
    os.environ["AWS_REGION"] = "eu-west-1"
    os.environ["AWS_DEFAULT_REGION"] = "eu-west-1"

    apply_fixtures()

    # test that the SSM parameter was created and contains full content
    ssm = boto3.client("ssm")
    response = ssm.get_parameter(Name="/test/ssm/environment", WithDecryption=True)
    assert "export FOO='BAR'" in response["Parameter"]["Value"]
    assert "export PASSWORD='super-secret'" in response["Parameter"]["Value"]
    assert "export TOKEN='abc123'" in response["Parameter"]["Value"]


def test_function_test_fixtures_raises_clear_error_when_ssm_upload_fails(notify_api, os_environ, mocker):
    huge_value = "x" * 9000
    mocker.patch("app.functional_tests_fixtures._create_db_objects", return_value=({"BIG": huge_value}, {}))

    ssm_client = mocker.Mock()
    ssm_client.put_parameter.side_effect = Exception("Parameter value too large")
    mocker.patch("app.functional_tests_fixtures.boto3.client", return_value=ssm_client)

    os.environ["SSM_UPLOAD_PATH"] = "/test/ssm/environment"

    with pytest.raises(Exception) as exc:
        apply_fixtures()

    assert "Failed to upload functional test environment to SSM path /test/ssm/environment" in str(exc.value)
    assert "payload size=" in str(exc.value)
    assert "Parameter value too large" in str(exc.value)


def test_function_test_fixtures_uploads_performance_env_to_separate_ssm_path(notify_api, os_environ, mocker):
    mocker.patch(
        "app.functional_tests_fixtures._create_db_objects",
        return_value=(
            {"FOO": "BAR"},
            {
                "PERFORMANCE_TESTS_SERVICE_API_KEY": "perf-key",
                "PERFORMANCE_TEST_EMAIL_TEMPLATE_ID": "perf-template-id",
            },
        ),
    )

    ssm_client = mocker.Mock()
    ssm_client.put_parameter.return_value = {"ResponseMetadata": {"HTTPStatusCode": 200}}
    mocker.patch("app.functional_tests_fixtures.boto3.client", return_value=ssm_client)

    os.environ["SSM_UPLOAD_PATH"] = "/test/ssm/functional-environment"
    os.environ["PERFORMANCE_SSM_UPLOAD_PATH"] = "/test/ssm/performance-environment"

    apply_fixtures()

    assert ssm_client.put_parameter.call_count == 2

    first_call_kwargs = ssm_client.put_parameter.call_args_list[0].kwargs
    second_call_kwargs = ssm_client.put_parameter.call_args_list[1].kwargs

    assert first_call_kwargs["Name"] == "/test/ssm/functional-environment"
    assert "export FOO='BAR'" in first_call_kwargs["Value"]
    assert "PERFORMANCE_TEST" not in first_call_kwargs["Value"]

    assert second_call_kwargs["Name"] == "/test/ssm/performance-environment"
    assert "export PERFORMANCE_TESTS_SERVICE_API_KEY='perf-key'" in second_call_kwargs["Value"]
    assert "export PERFORMANCE_TEST_EMAIL_TEMPLATE_ID='perf-template-id'" in second_call_kwargs["Value"]
    assert "export FOO='BAR'" not in second_call_kwargs["Value"]
