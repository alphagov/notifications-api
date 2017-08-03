from app import db
from app.dao.dao_utils import transactional
from app.models import InboundNumber


def dao_get_inbound_numbers():
    return InboundNumber.query.all()


def dao_get_available_inbound_numbers():
    return InboundNumber.query.filter(InboundNumber.active, InboundNumber.service_id.is_(None)).all()


def dao_get_inbound_number_for_service(service_id):
    return InboundNumber.query.filter(InboundNumber.service_id == service_id).all()


@transactional
def dao_allocate_inbound_number_to_service(service_id):
    available_numbers = InboundNumber.query.filter(
        InboundNumber.active, InboundNumber.service_id.is_(None)).all()

    if len(available_numbers) > 0:
        available_numbers[0].service_id = service_id

        db.session.add(available_numbers[0])
    else:
        raise IndexError('No inbound numbers available')
