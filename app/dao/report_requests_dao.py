from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, or_

from app import db
from app.constants import REPORT_REQUEST_IN_PROGRESS, REPORT_REQUEST_NOTIFICATIONS, REPORT_REQUEST_PENDING
from app.dao.dao_utils import autocommit
from app.models import ReportRequest


@autocommit
def dao_create_report_request(report_request: ReportRequest):
    db.session.add(report_request)
    return report_request


def dao_get_report_request_by_id(service_id: UUID, report_id: UUID) -> ReportRequest:
    return ReportRequest.query.filter_by(service_id=service_id, id=report_id).one()


def dao_get_oldest_ongoing_report_request(
    report_request: ReportRequest, timeout_minutes: int | None = None
) -> ReportRequest | None:
    query = ReportRequest.query.filter(
        ReportRequest.user_id == report_request.user_id,
        ReportRequest.service_id == report_request.service_id,
        ReportRequest.report_type == report_request.report_type,
        ReportRequest.status.in_([REPORT_REQUEST_PENDING, REPORT_REQUEST_IN_PROGRESS]),
    )

    # Apply timeout cutoff logic:
    # - If `updated_at` is set, we check if it's within the timeout window
    # - If `updated_at` is None, we fall back to using `created_at`
    # This ensures we exclude stale requests (older than `timeout` minutes),
    # while still considering those that may not have been updated yet.

    if timeout_minutes is not None:
        cutoff = datetime.utcnow() - timedelta(minutes=timeout_minutes)
        query = query.filter(
            or_(
                and_(
                    ReportRequest.updated_at.is_not(None),
                    ReportRequest.updated_at > cutoff,
                ),
                and_(
                    ReportRequest.updated_at.is_(None),
                    ReportRequest.created_at > cutoff,
                ),
            )
        )

    if report_request.report_type == REPORT_REQUEST_NOTIFICATIONS:
        query = query.filter(
            ReportRequest._parameter["notification_type"].astext == report_request.parameter["notification_type"],
            ReportRequest._parameter["notification_status"].astext == report_request.parameter["notification_status"],
        )

    return query.order_by(ReportRequest.created_at.asc()).first()


@autocommit
def dao_update_report_request(report_request: ReportRequest) -> ReportRequest:
    db.session.add(report_request)
    return report_request
