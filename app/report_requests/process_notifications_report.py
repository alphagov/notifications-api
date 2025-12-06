import csv
from io import StringIO
from typing import Any
from uuid import UUID

from flask import current_app
from notifications_utils.s3 import (
    S3_MULTIPART_UPLOAD_MIN_PART_SIZE,
    s3_multipart_upload_abort,
    s3_multipart_upload_complete,
    s3_multipart_upload_create,
    s3_multipart_upload_part,
)

from app.constants import NOTIFICATION_REPORT_REQUEST_MAPPING
from app.dao.notifications_dao import get_notifications_for_service
from app.dao.report_requests_dao import dao_get_report_request_by_id
from app.dao.service_data_retention_dao import fetch_service_data_retention_by_notification_type


class ReportRequestProcessor:
    def __init__(self, service_id: UUID, report_request_id: UUID):
        self.service_id = service_id
        self.report_request_id = report_request_id
        self.report_request = dao_get_report_request_by_id(service_id, report_request_id)
        self.notification_type = self.report_request.parameter["notification_type"]
        self.notification_status = self.report_request.parameter["notification_status"]
        self.page_size = current_app.config.get("REPORT_REQUEST_NOTIFICATIONS_CSV_BATCH_SIZE")
        self.s3_bucket = current_app.config["S3_BUCKET_REPORT_REQUESTS_DOWNLOAD"]
        self.filename = f"notifications_report/{report_request_id}.csv"
        self.upload_id: str | None = None
        self.parts: list[dict[str, Any]] = []
        self.part_number = 1
        self.csv_buffer = StringIO()
        self.csv_writer = csv.writer(self.csv_buffer)

    def process(self) -> None:
        self._initialize_csv()
        self._start_multipart_upload()

        try:
            self._fetch_and_upload_notifications()
            self._finalize_upload()
        except Exception as e:
            current_app.logger.exception("Error occurred while processing the report: %s", e)
            self._abort_upload()
            raise e

    def _initialize_csv(self) -> None:
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
        self.csv_writer.writerow(headers)

    def _start_multipart_upload(self) -> None:
        response = s3_multipart_upload_create(self.s3_bucket, self.filename)
        self.upload_id = response["UploadId"]

    def _fetch_and_upload_notifications(self) -> None:
        service_retention = fetch_service_data_retention_by_notification_type(self.service_id, self.notification_type)
        limit_days = service_retention.days_of_retention if service_retention else 7
        older_than = None
        is_notification = True
        while is_notification:
            serialized_notifications = self._fetch_serialized_notifications(limit_days, older_than)

            is_notification = len(serialized_notifications) != 0

            csv_data = self._convert_notifications_to_csv(serialized_notifications)
            self.csv_writer.writerows(csv_data)
            self._upload_csv_part_if_needed()
            older_than = serialized_notifications[-1]["id"] if is_notification else None
        # Upload any remaining data
        self._upload_remaining_data()

    def _fetch_serialized_notifications(self, limit_days: int, older_than: str | None) -> list[dict[str, Any]]:
        statuses = NOTIFICATION_REPORT_REQUEST_MAPPING[self.notification_status]

        notifications = get_notifications_for_service(
            service_id=self.service_id,
            filter_dict={
                "template_type": self.notification_type,
                "status": statuses,
            },
            page_size=self.page_size,
            count_pages=False,
            limit_days=limit_days,
            include_jobs=True,
            with_personalisation=False,
            include_from_test_key=False,
            error_out=False,
            include_one_off=True,
            older_than=older_than,
        )

        serialized_notifications = [notification.serialize_for_csv() for notification in notifications]
        return serialized_notifications

    def _convert_notifications_to_csv(self, serialized_notifications: list[dict[str, Any]]) -> list[tuple]:
        values = []
        for notification in serialized_notifications:
            values.append(
                (
                    # the recipient for precompiled letters is the full address block
                    notification["recipient"].splitlines()[0].lstrip().rstrip(" ,"),
                    notification["client_reference"],
                    notification["template_name"],
                    notification["template_type"],
                    notification["created_by_name"] or "",
                    notification["created_by_email_address"] or "",
                    notification["job_name"] or "",
                    notification["status"],
                    notification["created_at"],
                    notification["api_key_name"] or "",
                )
            )
        return values

    def _upload_csv_part_if_needed(self) -> None:
        data_bytes = self.csv_buffer.getvalue().encode("utf-8")
        if len(data_bytes) >= S3_MULTIPART_UPLOAD_MIN_PART_SIZE:
            self._upload_part(data_bytes)

            # Reset the buffer for the next part
            # truncate(0) does not reset the cursor so seek(0) is needed to reset the cursor
            self.csv_buffer.seek(0)
            self.csv_buffer.truncate(0)
            self.csv_writer = csv.writer(self.csv_buffer)

    def _upload_remaining_data(self) -> None:
        data_bytes = self.csv_buffer.getvalue().encode("utf-8")
        if len(data_bytes) > 0:
            self._upload_part(data_bytes)

    def _upload_part(self, data_bytes: bytes) -> None:
        response = s3_multipart_upload_part(
            part_number=self.part_number,
            bucket_name=self.s3_bucket,
            filename=self.filename,
            upload_id=self.upload_id,
            data_bytes=data_bytes,
        )
        extra = {
            "part_number": self.part_number,
            "report_request_id": self.report_request_id,
            "s3_bucket": self.s3_bucket,
            "s3_key": self.filename,
            "row_count": data_bytes.count(b"\n"),
        }
        current_app.logger.info(
            "Uploaded part %(part_number)s of report request %(report_request_id)s to bucket %(s3_bucket)s "
            "with filename %(s3_key)s. Rows per part: %(row_count)s",
            extra,
            extra=extra,
        )
        self.parts.append({"PartNumber": self.part_number, "ETag": response["ETag"]})
        self.part_number += 1

    def _finalize_upload(self) -> None:
        s3_multipart_upload_complete(
            bucket_name=self.s3_bucket,
            filename=self.filename,
            upload_id=self.upload_id,
            parts=self.parts,
        )
        extra = {
            "report_request_id": self.report_request_id,
            "s3_bucket": self.s3_bucket,
            "s3_key": self.filename,
            "part_count": len(self.parts),
        }
        current_app.logger.info(
            "Upload complete for report request %(report_request_id)s to bucket %(s3_bucket)s "
            "with filename %(s3_key)s. Total parts: %(part_count)s.",
            extra,
            extra=extra,
        )

    def _abort_upload(self) -> None:
        s3_multipart_upload_abort(
            bucket_name=self.s3_bucket,
            filename=self.filename,
            upload_id=self.upload_id,
        )
