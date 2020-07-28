from app import db
from app.models import ServiceWhitelist


def dao_fetch_service_guest_list(service_id):
    return ServiceWhitelist.query.filter(
        ServiceWhitelist.service_id == service_id).all()


def dao_add_and_commit_guest_list_contacts(objs):
    db.session.add_all(objs)
    db.session.commit()


def dao_remove_service_guest_list(service_id):
    return ServiceWhitelist.query.filter(
        ServiceWhitelist.service_id == service_id).delete()
