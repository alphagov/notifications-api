from sqlalchemy import desc, func

from app import db
from app.dao.dao_utils import autocommit
from app.models import UnsubscribeRequest, Service, UnsubscribeRequestReport


@autocommit
def create_unsubscribe_request_dao(unsubscribe_data):
    db.session.add(UnsubscribeRequest(**unsubscribe_data))


def get_unsubscribe_request_by_notification_id_dao(notification_id):
    return UnsubscribeRequest.query.filter_by(notification_id=notification_id).one()


def get_unsubscribe_requests_statistics_dao(service_id):
    unprocessed_batched_unsubscribe_requests_count = (
        db.session.query(UnsubscribeRequest)
        .join(UnsubscribeRequestReport, UnsubscribeRequestReport.id == UnsubscribeRequest.unsubscribe_request_report_id)
        .filter(UnsubscribeRequestReport.processed_by_service_at.is_(None), service_id == service_id)
        .count()
    )

    unprocessed_unbatched_unsubscribe_requests = (
        db.session.query(
            func.count(UnsubscribeRequest.id).label("count"),
            UnsubscribeRequest.unsubscribe_request_report_id,
            func.max(UnsubscribeRequest.created_at).label("datetime_of_latest_unsubscribe_request"),
        )
        .filter(UnsubscribeRequest.unsubscribe_request_report_id.is_(None), service_id == service_id)
        .group_by(UnsubscribeRequest.unsubscribe_request_report_id)
        .order_by(desc(UnsubscribeRequest.unsubscribe_request_report_id))
        .one()
    )

    unprocessed_unsubscribe_requests_count = (
        unprocessed_batched_unsubscribe_requests_count + unprocessed_unbatched_unsubscribe_requests["count"]
    )

    latest_unsubscribe_request_received_at = unprocessed_unbatched_unsubscribe_requests[
        "datetime_of_latest_unsubscribe_request"
    ]

    return {
        "count_of_pending_unsubscribe_requests": unprocessed_unsubscribe_requests_count,
        "datetime_of_latest_unsubscribe_request": latest_unsubscribe_request_received_at,
    }


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
