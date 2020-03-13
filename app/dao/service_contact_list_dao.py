from app import db
from app.models import ServiceContactList


def dao_get_contact_lists(service_id):
    contact_lists = ServiceContactList.query.filter_by(
        service_id=service_id
    ).order_by(
        ServiceContactList.created_at.desc()
    )
    return contact_lists.all()


def save_service_contact_list(service_contact_list):
    db.session.add(service_contact_list)
    db.session.commit()
