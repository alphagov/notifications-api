from datetime import datetime, timedelta
from io import BytesIO
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

from app import db
from app.constants import NOTIFICATION_REPORT_REQUEST_MAPPING
from app.dao.report_requests_dao import dao_get_report_request_by_id
from app.dao.service_data_retention_dao import fetch_service_data_retention_by_notification_type
from app.models import (
    Notification,
)
from app.utils import (
    midnight_n_days_ago,
)


class ReportRequestProcessor:
    def __init__(self, service_id: UUID, report_request_id: UUID):
        self.service_id = service_id
        self.report_request_id = report_request_id
        self.report_request = dao_get_report_request_by_id(service_id, report_request_id)

        self.notification_type = self.report_request.parameter["notification_type"]
        self.notification_status = self.report_request.parameter["notification_status"]
        self.s3_bucket = current_app.config["S3_BUCKET_REPORT_REQUESTS_DOWNLOAD"]
        self.filename = f"notifications_report/{report_request_id}.csv"

        self.upload_id: str | None = None
        self.parts: list[dict[str, Any]] = []
        self.part_number = 1
        self.csv_buffer = BytesIO()

    def process(self) -> None:
        self._start_multipart_upload()

        try:
            self._stream_query_to_s3()
            self._finalize_upload()
        except Exception as e:
            current_app.logger.exception("Error occurred while processing the report: %s", e)
            self._abort_upload()
            raise e

    def write(self, data: bytes) -> None:
        self.csv_buffer.write(data)
        if self.csv_buffer.tell() >= S3_MULTIPART_UPLOAD_MIN_PART_SIZE:
            self._upload_csv_part()

    def _start_multipart_upload(self) -> None:
        response = s3_multipart_upload_create(self.s3_bucket, self.filename)
        self.upload_id = response["UploadId"]

    def _stream_query_to_s3(self) -> None:
        service_retention = fetch_service_data_retention_by_notification_type(self.service_id, self.notification_type)
        limit_days = service_retention.days_of_retention if service_retention else 7

        requested_statuses = NOTIFICATION_REPORT_REQUEST_MAPPING[self.notification_status]
        filtered_statuses = Notification.substitute_status(requested_statuses)

        sa_connection = db.session.connection()
        raw_conn = sa_connection.connection
        cursor = raw_conn.cursor()

        try:
            start_time = midnight_n_days_ago(limit_days)
            end_time = datetime.utcnow()
            current_app.logger.info(
                "Generating report for service %s from %s to %s now %s",
                self.service_id,
                start_time,
                end_time,
                datetime.utcnow(),
            )
            chunk_interval = timedelta(hours=1)
            current_chunk_start = start_time

            is_first_chunk = True

            while current_chunk_start < end_time:
                current_chunk_end = min(current_chunk_start + chunk_interval, end_time)

                csv_format = "WITH CSV HEADER" if is_first_chunk else "WITH CSV"
                is_first_chunk = False

                sql = f"""
                COPY (
                    SELECT
                        n.to AS "Recipient",
                        n.client_reference AS "Reference",
                        t.name AS "Template",
                        n.notification_type AS "Type",
                        u.name AS "Sent by",
                        u.email_address AS "Sent by email",
                        j.original_file_name AS "Job",
                        CASE
                            WHEN n.notification_type = 'email' THEN
                                CASE n.notification_status
                                    WHEN 'failed' THEN 'Failed'
                                    WHEN 'technical-failure' THEN 'Technical failure'
                                    WHEN 'temporary-failure' THEN 'Inbox not accepting messages right now'
                                    WHEN 'permanent-failure' THEN 'Email address doesn’t exist'
                                    WHEN 'delivered' THEN 'Delivered'
                                    WHEN 'sending' THEN 'Sending'
                                    WHEN 'created' THEN 'Sending'
                                    WHEN 'sent' THEN 'Delivered'
                                    ELSE n.notification_status
                                END
                            WHEN n.notification_type = 'sms' THEN
                                CASE n.notification_status
                                    WHEN 'failed' THEN 'Failed'
                                    WHEN 'technical-failure' THEN 'Technical failure'
                                    WHEN 'temporary-failure' THEN 'Phone not accepting messages right now'
                                    WHEN 'permanent-failure' THEN 'Phone number doesn’t exist'
                                    WHEN 'delivered' THEN 'Delivered'
                                    WHEN 'sending' THEN 'Sending'
                                    WHEN 'created' THEN 'Sending'
                                    WHEN 'sent' THEN 'Sent internationally'
                                    ELSE n.notification_status
                                END
                            WHEN n.notification_type = 'letter' THEN
                                CASE n.notification_status
                                    WHEN 'technical-failure' THEN 'Technical failure'
                                    WHEN 'permanent-failure' THEN 'Permanent failure'
                                    WHEN 'sending' THEN 'Accepted'
                                    WHEN 'created' THEN 'Accepted'
                                    WHEN 'delivered' THEN 'Received'
                                    WHEN 'returned-letter' THEN 'Returned'
                                    ELSE n.notification_status
                                END
                            ELSE n.notification_status
                        END AS "Status",
                        n.created_at AS "Time",
                        a.name AS "API key name"
                    FROM notifications n
                    LEFT JOIN templates_history t ON n.template_id = t.id AND n.template_version = t.version
                    LEFT JOIN users u ON n.created_by_id = u.id
                    LEFT JOIN jobs j ON n.job_id = j.id
                    LEFT JOIN api_keys a ON n.api_key_id = a.id
                    WHERE n.service_id = %(service_id)s
                        AND n.notification_type = %(notification_type)s
                        AND n.notification_status IN %(statuses)s
                        AND n.created_at >= %(chunk_start)s
                        AND n.created_at < %(chunk_end)s
                    ORDER BY n.created_at ASC
                ) TO STDOUT {csv_format};
                """

                # Note: psycopg2 requires lists to be converted to tuples for the IN clause
                bound_sql = cursor.mogrify(
                    sql,
                    {
                        "service_id": str(self.service_id),
                        "notification_type": self.notification_type,
                        "statuses": tuple(filtered_statuses),
                        "chunk_start": current_chunk_start,
                        "chunk_end": current_chunk_end,
                    },
                )

                current_app.logger.info("Processing chunk from %s to %s", current_chunk_start, current_chunk_end)

                cursor.copy_expert(bound_sql, self)
                current_chunk_start = current_chunk_end

            if self.csv_buffer.tell() > 0:
                self._upload_csv_part()

        finally:
            cursor.close()

    def _upload_csv_part(self) -> None:
        data_bytes = self.csv_buffer.getvalue()

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

        self.csv_buffer.seek(0)
        self.csv_buffer.truncate(0)

    def _finalize_upload(self) -> None:
        s3_multipart_upload_complete(
            bucket_name=self.s3_bucket,
            filename=self.filename,
            upload_id=self.upload_id,
            parts=self.parts,
        )
        current_app.logger.info(
            "Upload complete for report request %s to bucket %s. Total parts: %s.",
            self.report_request_id,
            self.s3_bucket,
            len(self.parts),
        )

    def _abort_upload(self) -> None:
        if self.upload_id:
            s3_multipart_upload_abort(
                bucket_name=self.s3_bucket,
                filename=self.filename,
                upload_id=self.upload_id,
            )
