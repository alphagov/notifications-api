from app import db
from app.dao.dao_utils import autocommit
from app.models import UnsubscribeRequest, Service


@autocommit
def create_unsubscribe_request_dao(unsubscribe_data):
    db.session.add(UnsubscribeRequest(**unsubscribe_data))


def get_unsubscribe_request_by_notification_id_dao(notification_id):
    return UnsubscribeRequest.query.filter_by(notification_id=notification_id).one()


def get_count_of_unprocessed_requests(notification_id):
    return (
        db.session.query(
            UnsubscribeRequest.id.label("unsubscribe_request_id"),
        )
        .select_from(UnsubscribeRequest)
        .join(
            Service,
            Service.id == UnsubscribeRequest.service_id
        )
        .filter(UnsubscribeRequest.id == notification_id)
        .count()
    )
