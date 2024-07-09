from sqlalchemy import desc

from app import db
from app.dao.dao_utils import autocommit
from app.models import UnsubscribeRequest, UnsubscribeRequestReport


@autocommit
def create_unsubscribe_request_dao(unsubscribe_data):
    db.session.add(UnsubscribeRequest(**unsubscribe_data))


def get_unsubscribe_request_by_notification_id_dao(notification_id):
    return UnsubscribeRequest.query.filter_by(notification_id=notification_id).one()


def get_unsubscribe_request_reports_dao(service_id):
    return (
        UnsubscribeRequestReport.query.filter_by(service_id=service_id)
        .order_by(desc(UnsubscribeRequestReport.latest_timestamp))
        .all()
    )


def get_unbatched_unsubscribe_requests_dao(service_id):
    return UnsubscribeRequest.query.filter_by(service_id=service_id, unsubscribe_request_report_id=None).all()


@autocommit
def create_unsubscribe_request_reports_dao(unsubscribe_request_report):
    db.session.add(unsubscribe_request_report)
