from sqlalchemy import desc, func, or_

from app import db
from app.dao.dao_utils import autocommit
from app.models import UnsubscribeRequest, UnsubscribeRequestReport
from app.utils import midnight_n_days_ago


@autocommit
def create_unsubscribe_request_dao(unsubscribe_data):
    db.session.add(UnsubscribeRequest(**unsubscribe_data))


def get_unsubscribe_request_by_notification_id_dao(notification_id):
    return UnsubscribeRequest.query.filter_by(notification_id=notification_id).one()


def get_unsubscribe_requests_statistics_dao(service_id):
    """
    This method returns statistics for only unprocessed unsubscribe requests received
    in the last 7 days
    """
    return (
        db.session.query(
            func.count(UnsubscribeRequest.service_id).label("unprocessed_unsubscribe_requests_count"),
            UnsubscribeRequest.service_id,
            func.max(UnsubscribeRequest.created_at).label("datetime_of_latest_unsubscribe_request"),
        )
        .select_from(UnsubscribeRequest)
        .join(
            UnsubscribeRequestReport,
            UnsubscribeRequestReport.id == UnsubscribeRequest.unsubscribe_request_report_id,
            isouter=True,
        )
        .filter(
            or_(
                UnsubscribeRequest.unsubscribe_request_report_id.is_(None),
                UnsubscribeRequestReport.processed_by_service_at.is_(None),
            ),
            service_id == service_id,
            UnsubscribeRequest.created_at >= midnight_n_days_ago(7),
        )
        .group_by(UnsubscribeRequest.service_id)
        .one_or_none()
    )


def get_unsubscribe_request_reports_dao(service_id):
    return (
        UnsubscribeRequestReport.query.filter_by(service_id=service_id)
        .order_by(desc(UnsubscribeRequestReport.latest_timestamp))
        .all()
    )


def get_unbatched_unsubscribe_requests_dao(service_id):
    return (
        UnsubscribeRequest.query.filter_by(service_id=service_id, unsubscribe_request_report_id=None)
        .order_by(UnsubscribeRequest.created_at.desc())
        .all()
    )


@autocommit
def create_unsubscribe_request_reports_dao(unsubscribe_request_report):
    db.session.add(unsubscribe_request_report)
