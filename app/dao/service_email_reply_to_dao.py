from app import db
from app.dao.dao_utils import transactional
from app.models import ServiceEmailReplyTo


def create_or_update_email_reply_to(service_id, email_address):
    reply_to = dao_get_reply_to_by_service_id(service_id)
    if reply_to:
        reply_to.email_address = email_address
        dao_update_reply_to_email(reply_to)
    else:
        reply_to = ServiceEmailReplyTo(service_id=service_id, email_address=email_address)
        dao_create_reply_to_email_address(reply_to)


@transactional
def dao_create_reply_to_email_address(reply_to_email):
    db.session.add(reply_to_email)


def dao_get_reply_to_by_service_id(service_id):
    reply_to = db.session.query(
        ServiceEmailReplyTo
    ).filter(
        ServiceEmailReplyTo.service_id == service_id
    ).first()
    return reply_to


@transactional
def dao_update_reply_to_email(reply_to):
    db.session.add(reply_to)
