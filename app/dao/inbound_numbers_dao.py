from app import db
from app.dao.dao_utils import transactional
from app.models import InboundNumber


def dao_get_inbound_numbers():
    return InboundNumber.query.all()


def dao_get_available_inbound_numbers():
    return InboundNumber.query.filter(InboundNumber.active, InboundNumber.service_id.is_(None)).all()


def dao_get_inbound_number_for_service(service_id):
    return InboundNumber.query.filter(InboundNumber.service_id == service_id).first()


def dao_get_inbound_number(inbound_number_id):
    return InboundNumber.query.filter(InboundNumber.id == inbound_number_id).first()


@transactional
def dao_set_inbound_number_to_service(service_id, inbound_number):
    inbound_number.service_id = service_id
    db.session.add(inbound_number)


@transactional
def dao_set_inbound_number_active_flag(service_id, active):
    inbound_number = InboundNumber.query.filter(InboundNumber.service_id == service_id).first()
    inbound_number.active = active

    db.session.add(inbound_number)
