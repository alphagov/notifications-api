import csv
from io import StringIO

from flask import current_app
from notifications_utils.s3 import (
    s3_multipart_upload_abort,
    s3_multipart_upload_complete,
    s3_multipart_upload_create,
    s3_multipart_upload_part,
)

from app.constants import NOTIFICATION_REPORT_REQUEST_MAPPING
from app.dao.notifications_dao import get_notifications_for_service


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
    )

    serialized_notifications = [notification.serialize_for_csv() for notification in notifications]
    return serialized_notifications
