import json

from flask import current_app

from app.config import QueueNames
from app.constants import REPORT_REQUEST_NOTIFICATIONS
from app.dao.report_requests_dao import dao_create_report_request, dao_get_oldest_ongoing_report_request
from app.models import ReportRequest


def handle_report_request(
    report_request: ReportRequest,
) -> ReportRequest:
    if report_request.report_type == REPORT_REQUEST_NOTIFICATIONS:
        timeout_minutes = current_app.config.get("REPORT_REQUEST_NOTIFICATIONS_TIMEOUT_MINUTES")
    else:
        timeout_minutes = None

    existing_request = dao_get_oldest_ongoing_report_request(report_request, timeout=timeout_minutes)

    if existing_request:
        current_app.logger.info(
            "Found ongoing report request: %s for user %s with params %s",
            existing_request.id,
            existing_request.user_id,
            json.dumps(report_request.parameter, separators=(",", ":")),
        )

        return existing_request

    # No match found, create and enqueue a new one
    created_request = dao_create_report_request(report_request)

    current_app.logger.info(
        "Created new report request: %s for user %s with status %s and params %s",
        report_request.id,
        report_request.user_id,
        report_request.status,
        json.dumps(report_request.parameter, separators=(",", ":")),
    )

    # Enqueue the processing task
    # Check to see the state of this function as it currently is not in place
    process_report_request.apply_async(
        [str(report_request.service_id), str(report_request.id)],
        queue=QueueNames.REPORT_REQUESTS_NOTIFICATIONS,
    )

    current_app.logger.info(
        "Enqueued new report request: %s for user %s with status %s and params %s",
        report_request.id,
        report_request.user_id,
        report_request.status,
        json.dumps(report_request.parameter, separators=(",", ":")),
    )

    return created_request
