import csv
import io
from datetime import datetime, timedelta
from io import StringIO

import boto3
import pytest
from flask import current_app
from moto import mock_aws
from notifications_utils.s3 import S3_MULTIPART_UPLOAD_MIN_PART_SIZE, S3ObjectNotFound

from app.aws.s3 import get_s3_object
from app.constants import (
    KEY_TYPE_NORMAL,
    NOTIFICATION_CREATED,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_PERMANENT_FAILURE,
    NOTIFICATION_REQUEST_REPORT_ALL,
    NOTIFICATION_REQUEST_REPORT_DELIVERED,
    NOTIFICATION_REQUEST_REPORT_FAILED,
    NOTIFICATION_SENDING,
    NOTIFICATION_SENT,
    NOTIFICATION_TECHNICAL_FAILURE,
    REPORT_REQUEST_NOTIFICATIONS,
)
from app.dao.report_requests_dao import (
    dao_create_report_request,
)
from app.models import ReportRequest
from app.report_requests.process_notifications_report import (
    ReportRequestProcessor,
)
from app.utils import utc_string_to_bst_string
from tests.app.db import (
    create_api_key,
    create_job,
    create_notification,
    create_service,
    create_service_data_retention,
)
from tests.conftest import set_config


@pytest.fixture
@mock_aws
def mock_service(
    sample_email_template,
    sample_sms_template,
):
    service = create_service(check_if_service_exists=True)

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
            created_by_id=service.users[0].id,
        )
        create_notification(
            template=sample_email_template,
            status=NOTIFICATION_PERMANENT_FAILURE,
            api_key=api_key,
            created_at=datetime_now_2_days_before,
            created_by_id=service.users[0].id,
        )
        create_notification(
            template=sample_email_template,
            status=NOTIFICATION_DELIVERED,
            api_key=api_key,
            created_at=datetime_now_3_days_before,
            client_reference="email-reference",
            created_by_id=service.users[0].id,
        )
        create_notification(
            template=sample_email_template,
            status=NOTIFICATION_CREATED,
            api_key=api_key,
            created_at=datetime_now_4_days_before,
            client_reference="email-reference",
            created_by_id=service.users[0].id,
        )
        create_notification(
            template=sample_email_template,
            status=NOTIFICATION_SENT,
            api_key=api_key,
            created_at=datetime_now_5_days_before,
            created_by_id=service.users[0].id,
        )
        create_notification(
            template=sample_sms_template,
            status=NOTIFICATION_SENDING,
            api_key=api_key,
            created_at=datetime_now_4_days_before,
            client_reference="sms-reference",
            created_by_id=service.users[0].id,
        )
        create_notification(
            template=sample_sms_template,
            status=NOTIFICATION_CREATED,
            api_key=api_key,
            created_at=datetime_now_6_days_before,
            created_by_id=service.users[0].id,
        )
        create_notification(
            template=sample_sms_template,
            status=NOTIFICATION_TECHNICAL_FAILURE,
            api_key=api_key,
            created_at=datetime_now_2_days_before,
            client_reference="sms-reference",
            created_by_id=service.users[0].id,
        )
        create_notification(
            template=sample_sms_template,
            status=NOTIFICATION_DELIVERED,
            api_key=api_key,
            created_at=datetime_now,
            created_by_id=service.users[0].id,
        )

    report_bucket = current_app.config.get("S3_BUCKET_REPORT_REQUESTS_DOWNLOAD")
    s3 = boto3.client("s3", region_name="eu-west-1")
    s3.create_bucket(Bucket=report_bucket, CreateBucketConfiguration={"LocationConstraint": "eu-west-1"})

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


def test_initialize_csv_writes_headers(mock_processor, mock_service):
    mock_processor._initialize_csv()
    csv_contents = mock_processor.csv_buffer.getvalue()
    headers = [
        "Recipient",
        "Reference",
        "Template",
        "Type",
        "Sent by",
        "Sent by email",
        "Job",
        "Status",
        "Time",
        "API key name",
    ]
    for h in headers:
        assert h in csv_contents


def test_start_multipart_upload_sets_upload_id(mocker, mock_processor):
    mock_convert_notifications_to_csv = mocker.patch(
        "app.report_requests.process_notifications_report.s3_multipart_upload_create", return_value={"UploadId": "1234"}
    )
    mock_processor._start_multipart_upload()
    assert mock_processor.upload_id == "1234"
    mock_convert_notifications_to_csv.assert_called_once()


def test_fetch_and_upload_notifications(mocker, mock_processor):
    mock_upload = mocker.patch.object(mock_processor, "_upload_csv_part_if_needed")
    mock_upload_rem = mocker.patch.object(mock_processor, "_upload_remaining_data")
    mock_processor._fetch_and_upload_notifications()

    assert mock_upload.call_count == 2
    mock_upload_rem.assert_called_once()


def test_upload_part_adds_to_parts(mocker, mock_processor):
    mock_s3_upload_part = mocker.patch(
        "app.report_requests.process_notifications_report.s3_multipart_upload_part", return_value={"ETag": "etag123"}
    )
    mock_processor.upload_id = "upload123"
    test_data = b"some,data,for,csv\n" * 100
    mock_processor._upload_part(test_data)

    assert mock_processor.parts == [{"PartNumber": 1, "ETag": "etag123"}]
    assert mock_processor.part_number == 2
    mock_s3_upload_part.assert_called_once()


def test_finalize_upload_calls_s3(mocker, mock_processor):
    mock_complete = mocker.patch(
        "app.report_requests.process_notifications_report.s3_multipart_upload_complete",
        return_value={"ETag": "etag123"},
    )
    mock_processor.upload_id = "upload123"
    mock_processor.parts = [{"PartNumber": 1, "ETag": "etag123"}]
    mock_processor._finalize_upload()

    mock_complete.assert_called_once()


def test_abort_upload_calls_s3(mocker, mock_processor):
    mock_abort = mocker.patch("app.report_requests.process_notifications_report.s3_multipart_upload_abort")
    mock_processor.upload_id = "upload123"
    mock_processor._abort_upload()
    mock_abort.assert_called_once()


def test_convert_notifications_to_csv(mock_processor):
    notifications = [
        {
            "recipient": "user@email.com",
            "client_reference": "abc123",
            "template_name": "test-template",
            "template_type": "email",
            "created_by_name": "Admin User",
            "created_by_email_address": "admin@test.com",
            "job_name": "send emails",
            "status": "delivered",
            "created_at": "2025-04-01T00:00:00",
            "api_key_name": "TEST-API-KEY",
        }
    ]
    rows = mock_processor._convert_notifications_to_csv(notifications)
    assert rows[0][0] == "user@email.com"
    assert rows[0][1] == "abc123"
    assert rows[0][2] == "test-template"
    assert rows[0][3] == "email"
    assert rows[0][4] == "Admin User"
    assert rows[0][5] == "admin@test.com"
    assert rows[0][6] == "send emails"
    assert rows[0][7] == "delivered"
    assert rows[0][8] == "2025-04-01T00:00:00"
    assert rows[0][9] == "TEST-API-KEY"


def test_process_calls_abort_on_exception(mocker, mock_processor):
    mocker.patch.object(mock_processor, "_initialize_csv")
    mocker.patch.object(mock_processor, "_start_multipart_upload")
    mocker.patch.object(mock_processor, "_fetch_and_upload_notifications", side_effect=S3ObjectNotFound({}, ""))
    mock_abort = mocker.patch.object(mock_processor, "_abort_upload")

    with pytest.raises(S3ObjectNotFound):
        mock_processor.process()

    mock_abort.assert_called_once()


def test_process_does_not_call_abort_on_success(mocker, mock_processor):
    mocker.patch.object(mock_processor, "_initialize_csv")
    mocker.patch.object(mock_processor, "_start_multipart_upload")
    mocker.patch.object(mock_processor, "_fetch_and_upload_notifications")
    mock_finalize = mocker.patch.object(mock_processor, "_finalize_upload")
    mock_abort = mocker.patch.object(mock_processor, "_abort_upload")

    mock_processor.process()
    mock_finalize.assert_called_once()
    mock_abort.assert_not_called()


def test_upload_csv_part_if_needed_triggers_upload(mocker, mock_processor):
    mock_s3_upload_part = mocker.patch("app.report_requests.process_notifications_report.s3_multipart_upload_part")
    mock_processor.upload_id = "upload123"
    mock_processor.part_number = 1

    large_row = ",".join(["x" * 100] * 10)
    while len(mock_processor.csv_buffer.getvalue().encode("utf-8")) < S3_MULTIPART_UPLOAD_MIN_PART_SIZE:
        mock_processor.csv_writer.writerow([large_row] * 10)

    mock_processor._upload_csv_part_if_needed()

    mock_s3_upload_part.assert_called_once()


def test_upload_remaining_data_skips_if_empty(mocker, mock_processor):
    mock_s3_upload_part = mocker.patch("app.report_requests.process_notifications_report.s3_multipart_upload_part")
    mock_processor.csv_buffer = StringIO()  # empty
    mock_processor._upload_remaining_data()
    mock_s3_upload_part.assert_not_called()


def test_fetch_serialized_notifications_empty(mocker, mock_processor):
    mocker.patch("app.report_requests.process_notifications_report.get_notifications_for_service")
    result = mock_processor._fetch_serialized_notifications(1, 7)
    assert result == []


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
        processor = ReportRequestProcessor(service.id, report_request.id)
        processor.process()

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
        assert status_counter == expected_rows - 1  # exclude header


@pytest.mark.parametrize(
    ("page_size,notification_type,notification_report_request_status,"),
    [
        (
            2,
            "email",
            NOTIFICATION_REQUEST_REPORT_ALL,
        ),
    ],
)
@mock_aws
def test_process_report_request_should_contain_job_notification(
    page_size,
    notification_type,
    sample_user,
    notify_api,
    sample_email_template,
    notification_report_request_status,
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

    job = create_job(template=sample_email_template)

    # job notification
    create_notification(
        template=sample_email_template,
        client_reference="job-reference",
        status=NOTIFICATION_SENDING,
        job=job,
        job_row_number=2,
        created_at=datetime_now_1_day_before,
        created_by_id=service.users[0].id,
    )
    create_notification(
        template=sample_email_template,
        client_reference="no-job-reference",
        api_key=api_key,
        status=NOTIFICATION_SENDING,
        job_row_number=2,
        created_at=datetime_now_1_day_before,
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
        processor = ReportRequestProcessor(service.id, report_request.id)
        processor.process()

        original_pdf_object = get_s3_object(
            current_app.config["S3_BUCKET_REPORT_REQUESTS_DOWNLOAD"], f"notifications_report/{report_request.id}.csv"
        )
        content = original_pdf_object.get()["Body"].read().decode("utf-8")
        line_count = sum(1 for line in content.strip().splitlines() if line.strip())
        assert line_count == 3  # two rows + header

        reader = csv.DictReader(io.StringIO(content))

        headers = reader.fieldnames
        assert ",".join(headers) == expected_headers

        for row in reader:
            if row.get("Job"):
                assert row.get("Job") == "some.csv"
                assert row.get("Reference") == "job-reference"
            else:
                assert row.get("Job") == ""
                assert row.get("Reference") == "no-job-reference"
