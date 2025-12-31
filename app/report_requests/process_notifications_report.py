from uuid import UUID

from flask import current_app

from app.dao.report_requests_dao import dao_get_report_request_by_id
from app.dao.service_data_retention_dao import fetch_service_data_retention_by_notification_type
from app.report_requests.utils import (
    build_notifications_query,
    compile_query_for_copy,
    stream_query_to_s3,
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

    def process(self) -> None:
        try:
            self._stream_notifications_to_s3()
        except Exception as e:
            current_app.logger.exception("Error occurred while processing the report: %s", e)
            raise e

    def _stream_notifications_to_s3(self) -> None:
        service_retention = fetch_service_data_retention_by_notification_type(self.service_id, self.notification_type)
        limit_days = service_retention.days_of_retention if service_retention else 7

        query = build_notifications_query(
            service_id=self.service_id,
            notification_type=self.notification_type,
            language="en",
            notification_statuses=[self.notification_status] if self.notification_status != "all" else [],
            days_limit=limit_days,
        )

        copy_command = compile_query_for_copy(query)
        stream_query_to_s3(copy_command, self.s3_bucket, self.filename)

        extra = {
            "report_request_id": self.report_request_id,
            "s3_bucket": self.s3_bucket,
            "s3_key": self.filename,
        }
        current_app.logger.info(
            "Upload complete for report request %(report_request_id)s to bucket %(s3_bucket)s "
            "with filename %(s3_key)s.",
            extra,
            extra=extra,
        )
