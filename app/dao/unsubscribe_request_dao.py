from app import db
from app.dao.dao_utils import autocommit
from app.models import UnsubscribeRequest


@autocommit
def create_unsubscribe_request_dao(notification):
    unsubscribe_data = {  # noqa
        "notification_id": notification.id,
        "template_id": notification.template_id,
        "template_version": notification.template_version,
        "service_id": notification.service_id,
        "email_address": notification.to,
    }
    db.session.add(UnsubscribeRequest(**unsubscribe_data))


def get_unsubscribe_request_by_notification_id_dao(notification_id):
    return UnsubscribeRequest.query.filter_by(notification_id=notification_id).one()
