import csv
from io import StringIO

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


def process_report_request(service_id, report_request_id):
    report_request = dao_get_report_request_by_id(service_id, report_request_id)
    notification_type = report_request.parameter["notification_type"]
    notification_status = report_request.parameter["notification_status"]

    page_size = current_app.config.get("REPORT_REQUEST_NOTIFICATIONS_CSV_BATCH_SIZE")
    s3_bucket = current_app.config["S3_BUCKET_REPORT_REQUESTS_DOWNLOAD"]
    filename = f"notifications_report/{report_request_id}.csv"
    part_number = 1

    init_upload_response = s3_multipart_upload_create(s3_bucket, filename)
    upload_id = init_upload_response["UploadId"]
    parts = []

    csv_buffer = StringIO()
    csv_writer = csv.writer(csv_buffer)

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
    csv_writer.writerow(headers)

    try:
        service_retention = fetch_service_data_retention_by_notification_type(service_id, notification_type)
        limit_days = service_retention.days_of_retention if service_retention else 7
        page = 1

        while True:
            serialized_notifications = get_notifications_by_batch(
                service_id=service_id,
                template_type=notification_type,
                notification_status=notification_status,
                page=page,
                page_size=page_size,
                limit_days=limit_days,
            )

            csv_data = convert_notifications_to_csv(serialized_notifications)
            csv_writer.writerows(csv_data)

            csv_buffer.seek(0)
            data_bytes = csv_buffer.getvalue().encode("utf-8")

            # upload when the minimum upload part size exceeds
            if len(data_bytes) >= S3_MULTIPART_UPLOAD_MIN_PART_SIZE:
                upload_response = s3_multipart_upload_part(
                    part_number=part_number,
                    bucket_name=s3_bucket,
                    filename=filename,
                    upload_id=upload_id,
                    data_bytes=data_bytes,
                )
                parts.append({"PartNumber": part_number, "ETag": upload_response["ETag"]})
                part_number += 1

                # clear the buffer for the next batch
                csv_buffer.truncate(0)
                csv_buffer.seek(0)
            else:
                # move cursor to the end
                csv_buffer.seek(0, 2)

            page += 1

            if len(serialized_notifications) < page_size:
                break

        csv_buffer.seek(0)
        data_bytes = csv_buffer.getvalue().encode("utf-8")

        # upload any remaining data
        if len(data_bytes) > 0:
            upload_response = s3_multipart_upload_part(
                part_number=part_number,
                bucket_name=s3_bucket,
                filename=filename,
                upload_id=upload_id,
                data_bytes=data_bytes,
            )
            parts.append({"PartNumber": part_number, "ETag": upload_response["ETag"]})

        s3_multipart_upload_complete(
            bucket_name=s3_bucket,
            filename=filename,
            upload_id=upload_id,
            parts=parts,
        )

    except Exception as e:
        current_app.logger.exception("Error occurred for process notification request report: %s", e)
        s3_multipart_upload_abort(bucket_name=s3_bucket, filename=filename, upload_id=upload_id)
        raise e


def convert_notifications_to_csv(serialized_notifications):
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


def get_notifications_by_batch(service_id, notification_status, template_type, page, page_size, limit_days):
    statuses = NOTIFICATION_REPORT_REQUEST_MAPPING[notification_status]

    notifications = get_notifications_for_service(
        service_id=service_id,
        filter_dict={
            "template_type": template_type,
            "status": statuses,
        },
        page=page,
        page_size=page_size,
        limit_days=limit_days,
        error_out=False,
    )

    serialized_notifications = [notification.serialize_for_csv() for notification in notifications]
    return serialized_notifications
