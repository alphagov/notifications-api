import os
from tempfile import NamedTemporaryFile

import boto3
from moto import mock_aws

from app.functional_tests_fixtures import apply_fixtures
from tests.conftest import set_config_values


@mock_aws
def test_function_test_fixtures_apply(notify_api, notify_db_session, notify_service, os_environ):
    with NamedTemporaryFile(delete=False) as temp_file:
        temp_file_name = temp_file.name

    os.environ["REQUEST_BIN_API_TOKEN"] = "test_request_bin_token"
    os.environ["FUNCTIONAL_TEST_ENV_FILE"] = temp_file_name
    os.environ["SSM_UPLOAD_PATH"] = "/test/ssm/environment"
    # AWS are changing from AWS_DEFAULT_REGION to AWS_REGION for v2 clients. Set both for now.
    os.environ["AWS_REGION"] = "eu-west-1"
    os.environ["AWS_DEFAULT_REGION"] = "eu-west-1"
    try:
        # repeat twice to test idempotence
        for _ in range(2):
            with set_config_values(
                notify_api,
                {
                    "NOTIFY_ENVIRONMENT": "dev-env",
                    "MMG_INBOUND_SMS_USERNAME": ["test_mmg_username"],
                    "MMG_INBOUND_SMS_AUTH": ["test_mmg_password"],
                    "SECRET_KEY": "notify_secret_key",
                    "INTERNAL_CLIENT_API_KEYS": {"notify-functional-tests": ["functional-tests-secret-key"]},
                    "ADMIN_BASE_URL": "http://localhost:6012",
                    "API_HOST_NAME": "http://localhost:6011",
                    "FROM_NUMBER": "testing",
                },
            ):
                apply_fixtures()

            variables = {}
            full_file = ""
            with open(temp_file_name) as f:
                for line in f:
                    full_file += line
                    if not line.strip() or line.strip().startswith("#"):
                        continue
                    line = line.replace("export ", "")
                    key, value = line.strip().split("=")
                    if value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]
                    variables[key] = value

            assert variables["FUNCTIONAL_TESTS_API_HOST"] == "http://localhost:6011"
            assert variables["FUNCTIONAL_TESTS_ADMIN_HOST"] == "http://localhost:6012"
            assert variables["ENVIRONMENT"] == "dev-env"
            assert variables["FUNCTIONAL_TEST_EMAIL"] == "notify-tests-preview+dev-env@digital.cabinet-office.gov.uk"
            assert "FUNCTIONAL_TEST_PASSWORD" in variables
            assert variables["TEST_NUMBER"] == "07700900001"
            assert variables["NOTIFY_SERVICE_API_KEY"].startswith("govuk_notify-")
            assert (
                variables["FUNCTIONAL_TESTS_SERVICE_EMAIL"]
                == "notify-tests-preview+dev-env-admin-tests@digital.cabinet-office.gov.uk"
            )
            assert (
                variables["FUNCTIONAL_TESTS_SERVICE_EMAIL_AUTH_ACCOUNT"]
                == "notify-tests-preview+dev-env-email-auth@digital.cabinet-office.gov.uk"
            )
            assert "FUNCTIONAL_TESTS_SERVICE_EMAIL_PASSWORD" in variables
            assert variables["FUNCTIONAL_TESTS_SERVICE_NUMBER"] == "07700900501"
            assert "FUNCTIONAL_TESTS_SERVICE_ID" in variables
            assert variables["FUNCTIONAL_TESTS_SERVICE_NAME"] == "Functional Tests"
            assert "FUNCTIONAL_TESTS_ORGANISATION_ID" in variables
            assert variables["FUNCTIONAL_TESTS_SERVICE_API_KEY"].startswith("functional_tests_service_live_key-")
            assert variables["FUNCTIONAL_TESTS_SERVICE_API_TEST_KEY"].startswith("functional_tests_service_test_key-")
            assert variables["FUNCTIONAL_TESTS_API_AUTH_SECRET"] == "functional-tests-secret-key"
            assert (
                variables["FUNCTIONAL_TESTS_SERVICE_EMAIL_REPLY_TO"]
                == "notify-tests-preview+dev-env-reply-to@digital.cabinet-office.gov.uk"
            )
            assert variables["FUNCTIONAL_TESTS_SERVICE_INBOUND_NUMBER"] == "07700900500"
            assert "FUNCTIONAL_TEST_SMS_TEMPLATE_ID" in variables
            assert "FUNCTIONAL_TEST_EMAIL_TEMPLATE_ID" in variables
            assert "FUNCTIONAL_TEST_LETTER_TEMPLATE_ID" in variables
            assert variables["MMG_INBOUND_SMS_USERNAME"] == "test_mmg_username"
            assert variables["MMG_INBOUND_SMS_AUTH"] == "test_mmg_password"
            assert variables["REQUEST_BIN_API_TOKEN"] == "test_request_bin_token"

            # test that the SSM parameter was created and contains the same as the file
            ssm = boto3.client("ssm")
            response = ssm.get_parameter(Name="/test/ssm/environment", WithDecryption=True)
            assert response["Parameter"]["Value"] == full_file

    finally:
        os.remove(temp_file_name)
