import boto3
import botocore
import pytest
from flask import current_app
from freezegun import freeze_time
from moto import mock_aws

from app.aws.s3 import file_exists
from app.constants import (
    KEY_TYPE_NORMAL,
    REPORT_REQUEST_NOTIFICATIONS,
)
from app.dao.notifications_dao import (
    get_notifications_for_service,
)
from app.dao.report_requests_dao import (
    dao_create_report_request,
)
from app.models import ReportRequest
from app.report_requests.process_notifications_report import (
    convert_notifications_to_csv,
    get_notifications_by_batch,
    process_report_request,
)
from tests.app.db import (
    create_api_key,
    create_notification,
    create_service,
    create_service_data_retention,
)


def test_convert_notifications_to_csv_when_empty_notifications(sample_sms_template):
    csv_data = convert_notifications_to_csv([])

    expected_csv = []

    assert expected_csv == csv_data


@freeze_time("2025-03-19 18:25:33")
def test_convert_notifications_to_csv_values(sample_sms_template):
    service = create_service(check_if_service_exists=True)
    api_key = create_api_key(service=service, key_type=KEY_TYPE_NORMAL, id="8e33368c-3965-4ae1-ab55-4f9d3275f84d")

    create_notification(template=sample_sms_template, status="delivered", api_key=api_key)
    create_notification(template=sample_sms_template, status="sending", api_key=api_key)
    create_notification(template=sample_sms_template, status="sending", api_key=api_key)
    create_notification(template=sample_sms_template, status="created", api_key=api_key)
    create_notification(template=sample_sms_template, status="delivered", api_key=api_key)

    notifications = get_notifications_for_service(service.id)
    serialized_notifications = [notification.serialize_for_csv() for notification in notifications]
    csv_data = convert_notifications_to_csv(serialized_notifications)

    expected_csv = [
        (
            "+447700900855",
            "",
            "Template Name",
            "sms",
            "",
            "",
            "",
            "Delivered",
            "2025-03-19 18:25:33",
            "normal api key 8e33368c-3965-4ae1-ab55-4f9d3275f84d",
        ),
        (
            "+447700900855",
            "",
            "Template Name",
            "sms",
            "",
            "",
            "",
            "Sending",
            "2025-03-19 18:25:33",
            "normal api key 8e33368c-3965-4ae1-ab55-4f9d3275f84d",
        ),
        (
            "+447700900855",
            "",
            "Template Name",
            "sms",
            "",
            "",
            "",
            "Sending",
            "2025-03-19 18:25:33",
            "normal api key 8e33368c-3965-4ae1-ab55-4f9d3275f84d",
        ),
        (
            "+447700900855",
            "",
            "Template Name",
            "sms",
            "",
            "",
            "",
            "Sending",
            "2025-03-19 18:25:33",
            "normal api key 8e33368c-3965-4ae1-ab55-4f9d3275f84d",
        ),
        (
            "+447700900855",
            "",
            "Template Name",
            "sms",
            "",
            "",
            "",
            "Delivered",
            "2025-03-19 18:25:33",
            "normal api key 8e33368c-3965-4ae1-ab55-4f9d3275f84d",
        ),
    ]

    assert expected_csv == csv_data


@pytest.mark.parametrize(
    "page_size, page, expected_notifications, status",
    [
        (5, 1, 5, "all"),
        (2, 2, 1, "sending"),
        (2, 1, 2, "delivered"),
    ],
)
def test_get_notifications_by_batch(
    page_size, page, status, expected_notifications, sample_email_template, sample_sms_template
):
    service = create_service(check_if_service_exists=True)
    create_service_data_retention(service=service)
    api_key = create_api_key(service=service, key_type=KEY_TYPE_NORMAL, id="8e33368c-3965-4ae1-ab55-4f9d3275f84d")

    create_notification(template=sample_email_template, status="sending", api_key=api_key)
    create_notification(template=sample_sms_template, status="sending", api_key=api_key)
    create_notification(template=sample_email_template, status="delivered", api_key=api_key)
    create_notification(template=sample_email_template, status="delivered", api_key=api_key)
    create_notification(template=sample_email_template, status="sending", api_key=api_key)
    create_notification(template=sample_email_template, status="sending", api_key=api_key)
    create_notification(template=sample_email_template, status="created", api_key=api_key)
    create_notification(template=sample_email_template, status="sent", api_key=api_key)

    notifications = get_notifications_by_batch(
        service_id=service.id, status=status, template_type="email", page=page, page_size=page_size, limit_days=2
    )
    assert len(notifications) == expected_notifications


@mock_aws
def test_process_report_request(mocker, sample_user):
    service = create_service(check_if_service_exists=True)
    notification_type = "email"
    service_retention = create_service_data_retention(service=service, notification_type=notification_type)
    mock_get_notifications_by_batch = mocker.patch(
        "app.report_requests.process_notifications_report.get_notifications_by_batch", return_value=[]
    )
    mock_convert_notifications_to_csv = mocker.patch(
        "app.report_requests.process_notifications_report.convert_notifications_to_csv", return_value=[]
    )

    report_bucket = current_app.config.get("S3_BUCKET_REPORT_REQUESTS_DOWNLOAD")
    s3 = boto3.client("s3", region_name="eu-west-1")
    s3.create_bucket(Bucket=report_bucket, CreateBucketConfiguration={"LocationConstraint": "eu-west-1"})

    sample_parameter = {"notification_type": notification_type, "notification_status": "all"}
    report_request = ReportRequest(
        user_id=sample_user.id,
        service_id=service.id,
        report_type=REPORT_REQUEST_NOTIFICATIONS,
        parameter=sample_parameter,
    )
    dao_create_report_request(report_request)

    process_report_request(service.id, report_request.id)

    mock_get_notifications_by_batch.assert_called_once_with(
        service_id=service.id,
        template_type=notification_type,
        status="all",
        page=1,
        page_size=current_app.config.get("REPORT_REQUEST_NOTIFICATIONS_CSV_BATCH_SIZE"),
        limit_days=service_retention.days_of_retention,
    )
    mock_convert_notifications_to_csv.assert_called_once()

    assert (
        file_exists(
            current_app.config.get("S3_BUCKET_REPORT_REQUESTS_DOWNLOAD"),
            f"notifications_report/{report_request.id}.csv",
        )
        is True
    )


@mock_aws
def test_process_report_request_should_abort_s3_upload_on_error(mocker, sample_user):
    service = create_service(check_if_service_exists=True)
    notification_type = "email"
    service_retention = create_service_data_retention(service=service, notification_type=notification_type)

    mock_get_notifications_by_batch = mocker.patch(
        "app.report_requests.process_notifications_report.get_notifications_by_batch", return_value=[]
    )
    mock_convert_notifications_to_csv = mocker.patch(
        "app.report_requests.process_notifications_report.convert_notifications_to_csv",
    )

    mock_s3_multipart_upload_create = mocker.patch(
        "app.report_requests.process_notifications_report.s3_multipart_upload_create"
    )
    mock_s3_multipart_upload_abort = mocker.patch(
        "app.report_requests.process_notifications_report.s3_multipart_upload_abort"
    )
    mock_s3_multipart_upload_part = mocker.patch(
        "app.report_requests.process_notifications_report.s3_multipart_upload_part",
        side_effect=botocore.exceptions.ClientError({"Error": {"Code": 500}}, "Bad exception"),
    )
    mock_s3_multipart_upload_complete = mocker.patch(
        "app.report_requests.process_notifications_report.s3_multipart_upload_complete"
    )

    report_bucket = current_app.config.get("S3_BUCKET_REPORT_REQUESTS_DOWNLOAD")
    s3 = boto3.client("s3", region_name="eu-west-1")
    s3.create_bucket(Bucket=report_bucket, CreateBucketConfiguration={"LocationConstraint": "eu-west-1"})

    sample_parameter = {"notification_type": notification_type, "notification_status": "all"}
    report_request = ReportRequest(
        user_id=sample_user.id,
        service_id=service.id,
        report_type=REPORT_REQUEST_NOTIFICATIONS,
        parameter=sample_parameter,
    )
    dao_create_report_request(report_request)

    with pytest.raises(botocore.exceptions.ClientError):
        process_report_request(service.id, report_request.id)

    mock_get_notifications_by_batch.assert_called_once_with(
        service_id=service.id,
        template_type=notification_type,
        status="all",
        page=1,
        page_size=current_app.config.get("REPORT_REQUEST_NOTIFICATIONS_CSV_BATCH_SIZE"),
        limit_days=service_retention.days_of_retention,
    )
    mock_convert_notifications_to_csv.assert_called_once()

    mock_s3_multipart_upload_create.assert_called_once()
    mock_s3_multipart_upload_part.assert_called_once()
    mock_s3_multipart_upload_abort.assert_called_once()
    assert mock_s3_multipart_upload_complete.called is False

    assert (
        file_exists(
            current_app.config.get("S3_BUCKET_REPORT_REQUESTS_DOWNLOAD"),
            f"notifications_report/{report_request.id}.csv",
        )
        is False
    )
