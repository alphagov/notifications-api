from app import db
from app.models import ServiceGuestList


def dao_fetch_service_guest_list(service_id):
    return ServiceGuestList.query.filter(
        ServiceGuestList.service_id == service_id).all()


def dao_add_and_commit_guest_list_contacts(objs):
    db.session.add_all(objs)
    db.session.commit()


def dao_remove_service_guest_list(service_id):
    return ServiceGuestList.query.filter(
        ServiceGuestList.service_id == service_id).delete()
