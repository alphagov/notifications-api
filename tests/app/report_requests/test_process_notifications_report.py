import csv
import io
from datetime import datetime, timedelta

import boto3
import botocore
import pytest
from flask import current_app
from freezegun import freeze_time
from moto import mock_aws

from app.aws.s3 import file_exists, get_s3_object
from app.constants import (
    KEY_TYPE_NORMAL,
    NOTIFICATION_CREATED,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_PERMANENT_FAILURE,
    NOTIFICATION_REQUEST_REPORT_ALL,
    NOTIFICATION_REQUEST_REPORT_DELIVERED,
    NOTIFICATION_REQUEST_REPORT_FAILED,
    NOTIFICATION_REQUEST_REPORT_SENDING,
    NOTIFICATION_SENDING,
    NOTIFICATION_SENT,
    NOTIFICATION_TECHNICAL_FAILURE,
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
from app.utils import utc_string_to_bst_string
from tests.app.db import (
    create_api_key,
    create_notification,
    create_service,
    create_service_data_retention,
)
from tests.conftest import set_config


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
    "page_size, page, expected_notifications, notification_report_request_status",
    [
        (5, 1, 5, NOTIFICATION_REQUEST_REPORT_ALL),
        (2, 2, 2, NOTIFICATION_REQUEST_REPORT_SENDING),
        (1, 1, 1, NOTIFICATION_REQUEST_REPORT_SENDING),
        (2, 1, 2, NOTIFICATION_REQUEST_REPORT_DELIVERED),
    ],
)
def test_get_notifications_by_batch(
    page_size,
    page,
    notification_report_request_status,
    expected_notifications,
    sample_email_template,
    sample_sms_template,
):
    service = create_service(check_if_service_exists=True)
    create_service_data_retention(service=service)
    api_key = create_api_key(service=service, key_type=KEY_TYPE_NORMAL, id="8e33368c-3965-4ae1-ab55-4f9d3275f84d")

    create_notification(template=sample_email_template, status=NOTIFICATION_SENDING, api_key=api_key)
    create_notification(template=sample_sms_template, status=NOTIFICATION_SENDING, api_key=api_key)
    create_notification(template=sample_email_template, status=NOTIFICATION_DELIVERED, api_key=api_key)
    create_notification(template=sample_email_template, status=NOTIFICATION_DELIVERED, api_key=api_key)
    create_notification(template=sample_email_template, status=NOTIFICATION_SENDING, api_key=api_key)
    create_notification(template=sample_email_template, status=NOTIFICATION_SENDING, api_key=api_key)
    create_notification(template=sample_email_template, status=NOTIFICATION_CREATED, api_key=api_key)
    create_notification(template=sample_email_template, status=NOTIFICATION_SENT, api_key=api_key)

    notifications = get_notifications_by_batch(
        service_id=service.id,
        notification_status=notification_report_request_status,
        template_type="email",
        page=page,
        page_size=page_size,
        limit_days=2,
    )
    assert len(notifications) == expected_notifications


@pytest.mark.parametrize(
    "page_size, notification_type, data_size_mb",
    [
        (1, "sms", 6),
        (2, "email", 4),
        (5, "letter", 6),
        (2, "sms", 2),
    ],
)
@mock_aws
def test_process_report_request(
    mocker,
    page_size,
    notification_type,
    data_size_mb,
    sample_user,
    notify_api,
):
    service = create_service(check_if_service_exists=True)
    service_retention = 4

    create_service_data_retention(
        service=service, notification_type=notification_type, days_of_retention=service_retention
    )

    test_notification_str = (
        "test_recipient",
        "",
        "Test Template Name",
        "test_type",
        "",
        "",
        "",
        "Sending",
        "2025-04-02 18:37:54",
        "normal api-key-test",
    )
    rows_needed = (
        (data_size_mb * 1024 * 1024) // len(",".join(test_notification_str))
    ) + 1  # calculate the size needed

    csv_data = []
    for _i in range(rows_needed):
        csv_data.append(test_notification_str)

    sample_parameter = {"notification_type": notification_type, "notification_status": NOTIFICATION_REQUEST_REPORT_ALL}

    mock_get_notifications_by_batch = mocker.patch(
        "app.report_requests.process_notifications_report.get_notifications_by_batch", return_value=[]
    )
    mock_convert_notifications_to_csv = mocker.patch(
        "app.report_requests.process_notifications_report.convert_notifications_to_csv", return_value=csv_data
    )

    report_bucket = current_app.config.get("S3_BUCKET_REPORT_REQUESTS_DOWNLOAD")
    s3 = boto3.client("s3", region_name="eu-west-1")
    s3.create_bucket(Bucket=report_bucket, CreateBucketConfiguration={"LocationConstraint": "eu-west-1"})

    report_request = ReportRequest(
        user_id=sample_user.id,
        service_id=service.id,
        report_type=REPORT_REQUEST_NOTIFICATIONS,
        parameter=sample_parameter,
    )
    dao_create_report_request(report_request)

    with set_config(notify_api, "REPORT_REQUEST_NOTIFICATIONS_CSV_BATCH_SIZE", page_size):
        process_report_request(service.id, report_request.id)

        mock_get_notifications_by_batch.assert_called_once_with(
            service_id=service.id,
            template_type=notification_type,
            notification_status=NOTIFICATION_REQUEST_REPORT_ALL,
            page=1,
            page_size=page_size,
            limit_days=service_retention,
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

    sample_parameter = {"notification_type": notification_type, "notification_status": NOTIFICATION_REQUEST_REPORT_ALL}
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
        notification_status=NOTIFICATION_REQUEST_REPORT_ALL,
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


@pytest.mark.parametrize(
    (
        "page_size,"
        "notification_type,"
        "notification_report_request_status,"
        "expected_rows,"
        "expected_statuses,"
        "expected_recipient,"
        "expected_template_type,"
        "client_reference"
    ),
    [
        (
            1,
            "sms",
            NOTIFICATION_REQUEST_REPORT_ALL,
            31,
            ["Delivered", "Sending", "Technical failure"],
            "+447700900855",
            "Template Name",
            "",
        ),
        (
            2,
            "email",
            NOTIFICATION_REQUEST_REPORT_ALL,
            51,
            ["Delivered", "Sending", "Email address doesn’t exist"],
            "test@example.com",
            "Email Template Name",
            "",
        ),
        (
            4,
            "sms",
            NOTIFICATION_REQUEST_REPORT_DELIVERED,
            11,
            ["Delivered"],
            "+447700900855",
            "Template Name",
            "sms-reference",
        ),
        (
            5,
            "email",
            NOTIFICATION_REQUEST_REPORT_FAILED,
            11,
            ["Email address doesn’t exist"],
            "test@example.com",
            "Email Template Name",
            "email-reference",
        ),
        (3, "letter", NOTIFICATION_REQUEST_REPORT_FAILED, 1, [], "", "", ""),
    ],
)
@mock_aws
def test_process_report_request_should_return_correct_rows(
    page_size,
    notification_type,
    sample_user,
    notify_api,
    sample_email_template,
    notification_report_request_status,
    expected_rows,
    expected_statuses,
    expected_recipient,
    expected_template_type,
    sample_sms_template,
    client_reference,
):
    expected_headers = "Recipient,Reference,Template,Type,Sent by,Sent by email,Job,Status,Time,API key name"

    service = create_service(check_if_service_exists=True)
    service_retention = 5

    create_service_data_retention(
        service=service, notification_type=notification_type, days_of_retention=service_retention
    )

    api_key = create_api_key(service=service, key_type=KEY_TYPE_NORMAL, id="8e33368c-3965-4ae1-ab55-4f9d3275f84d")

    datetime_now = datetime.now()
    datetime_now_1_day_before = datetime_now - timedelta(days=1)
    datetime_now_2_days_before = datetime_now - timedelta(days=2)
    datetime_now_3_days_before = datetime_now - timedelta(days=3)
    datetime_now_4_days_before = datetime_now - timedelta(days=4)
    datetime_now_5_days_before = datetime_now - timedelta(days=5)
    datetime_now_6_days_before = datetime_now - timedelta(days=6)

    for _i in range(10):
        create_notification(
            template=sample_email_template,
            status=NOTIFICATION_SENDING,
            api_key=api_key,
            created_at=datetime_now_1_day_before,
            client_reference=client_reference,
            created_by_id=service.users[0].id,
        )
        create_notification(
            template=sample_email_template,
            status=NOTIFICATION_PERMANENT_FAILURE,
            api_key=api_key,
            created_at=datetime_now_2_days_before,
            client_reference=client_reference,
            created_by_id=service.users[0].id,
        )
        create_notification(
            template=sample_email_template,
            status=NOTIFICATION_DELIVERED,
            api_key=api_key,
            created_at=datetime_now_3_days_before,
            client_reference=client_reference,
            created_by_id=service.users[0].id,
        )
        create_notification(
            template=sample_email_template,
            status=NOTIFICATION_CREATED,
            api_key=api_key,
            created_at=datetime_now_4_days_before,
            client_reference=client_reference,
            created_by_id=service.users[0].id,
        )
        create_notification(
            template=sample_email_template,
            status=NOTIFICATION_SENT,
            api_key=api_key,
            created_at=datetime_now_5_days_before,
            client_reference=client_reference,
            created_by_id=service.users[0].id,
        )
        create_notification(
            template=sample_sms_template,
            status=NOTIFICATION_SENDING,
            api_key=api_key,
            created_at=datetime_now_4_days_before,
            client_reference=client_reference,
            created_by_id=service.users[0].id,
        )
        create_notification(
            template=sample_sms_template,
            status=NOTIFICATION_CREATED,
            api_key=api_key,
            created_at=datetime_now_6_days_before,
            client_reference=client_reference,
            created_by_id=service.users[0].id,
        )
        create_notification(
            template=sample_sms_template,
            status=NOTIFICATION_TECHNICAL_FAILURE,
            api_key=api_key,
            created_at=datetime_now_2_days_before,
            client_reference=client_reference,
            created_by_id=service.users[0].id,
        )
        create_notification(
            template=sample_sms_template,
            status=NOTIFICATION_DELIVERED,
            api_key=api_key,
            created_at=datetime_now,
            client_reference=client_reference,
            created_by_id=service.users[0].id,
        )

    sample_parameter = {
        "notification_type": notification_type,
        "notification_status": notification_report_request_status,
    }

    report_bucket = current_app.config.get("S3_BUCKET_REPORT_REQUESTS_DOWNLOAD")
    s3 = boto3.client("s3", region_name="eu-west-1")
    s3.create_bucket(Bucket=report_bucket, CreateBucketConfiguration={"LocationConstraint": "eu-west-1"})

    report_request = ReportRequest(
        user_id=sample_user.id,
        service_id=service.id,
        report_type=REPORT_REQUEST_NOTIFICATIONS,
        parameter=sample_parameter,
    )
    dao_create_report_request(report_request)

    with set_config(notify_api, "REPORT_REQUEST_NOTIFICATIONS_CSV_BATCH_SIZE", page_size):
        process_report_request(service.id, report_request.id)

        original_pdf_object = get_s3_object(
            current_app.config["S3_BUCKET_REPORT_REQUESTS_DOWNLOAD"], f"notifications_report/{report_request.id}.csv"
        )
        content = original_pdf_object.get()["Body"].read().decode("utf-8")
        line_count = sum(1 for line in content.strip().splitlines() if line.strip())
        reader = csv.DictReader(io.StringIO(content))

        headers = reader.fieldnames
        assert ",".join(headers) == expected_headers

        status_counter = 0
        for row in reader:
            created_at = row.get("Time")
            assert created_at in [
                utc_string_to_bst_string(datetime_now),
                utc_string_to_bst_string(datetime_now_1_day_before),
                utc_string_to_bst_string(datetime_now_2_days_before),
                utc_string_to_bst_string(datetime_now_3_days_before),
                utc_string_to_bst_string(datetime_now_4_days_before),
                utc_string_to_bst_string(datetime_now_5_days_before),
            ]

            assert row.get("Type") == notification_type
            assert row.get("Recipient") == expected_recipient
            assert row.get("Reference") == client_reference
            assert row.get("Template") == expected_template_type
            assert row.get("Sent by") == service.users[0].name
            assert row.get("Sent by email") == service.users[0].email_address
            assert row.get("API key name") == api_key.name

            status = row.get("Status")
            if status in expected_statuses:
                status_counter += 1

        assert line_count == expected_rows
        assert status_counter == expected_rows - 1 # exclude header
