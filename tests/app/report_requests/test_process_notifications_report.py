import pytest
from flask import current_app
from moto import mock_aws

from app.constants import (
    KEY_TYPE_NORMAL,
    NOTIFICATION_REQUEST_REPORT_ALL,
    REPORT_REQUEST_NOTIFICATIONS,
)
from app.dao.report_requests_dao import (
    dao_create_report_request,
)
from app.models import ReportRequest
from app.report_requests.process_notifications_report import (
    ReportRequestProcessor,
)
from tests.app.db import (
    create_api_key,
    create_service,
)


@pytest.fixture
@mock_aws
def mock_service(
    sample_email_template,
    sample_sms_template,
):
    service = create_service(check_if_service_exists=True)
    create_api_key(service=service, key_type=KEY_TYPE_NORMAL, id="8e33368c-3965-4ae1-ab55-4f9d3275f84d")
    return service


@pytest.fixture
def mock_processor(sample_user, mock_service):
    sample_parameter = {
        "notification_type": "sms",
        "notification_status": NOTIFICATION_REQUEST_REPORT_ALL,
    }

    report_request = ReportRequest(
        user_id=sample_user.id,
        service_id=mock_service.id,
        report_type=REPORT_REQUEST_NOTIFICATIONS,
        parameter=sample_parameter,
    )
    dao_create_report_request(report_request)

    return ReportRequestProcessor(mock_service.id, report_request.id)


def test_process_calls_stream_notifications_to_s3(mocker, mock_processor):
    mock_stream = mocker.patch("app.report_requests.process_notifications_report.stream_query_to_s3")
    mock_compile = mocker.patch(
        "app.report_requests.process_notifications_report.compile_query_for_copy", return_value="COPY command"
    )
    mock_build_query = mocker.patch(
        "app.report_requests.process_notifications_report.build_notifications_query", return_value="query"
    )

    mock_processor.process()

    mock_build_query.assert_called_once()
    mock_compile.assert_called_once_with("query")
    mock_stream.assert_called_once_with(
        "COPY command",
        current_app.config["S3_BUCKET_REPORT_REQUESTS_DOWNLOAD"],
        f"notifications_report/{mock_processor.report_request_id}.csv",
    )


def test_process_logs_error_on_exception(mocker, mock_processor):
    mocker.patch(
        "app.report_requests.process_notifications_report.stream_query_to_s3", side_effect=Exception("Test error")
    )
    mock_logger = mocker.patch("app.report_requests.process_notifications_report.current_app.logger.exception")

    with pytest.raises(Exception, match="Test error"):
        mock_processor.process()

    mock_logger.assert_called_once_with("Error occurred while processing the report: %s", mocker.ANY)
