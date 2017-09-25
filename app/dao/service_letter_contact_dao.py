from app import db
from app.dao.dao_utils import transactional
from app.errors import InvalidRequest
from app.models import ServiceLetterContact


def dao_get_letter_contacts_by_service_id(service_id):
    letter_contacts = db.session.query(
        ServiceLetterContact
    ).filter(
        ServiceLetterContact.service_id == service_id
    ).order_by(
        ServiceLetterContact.created_at
    ).all()

    return letter_contacts


def create_or_update_letter_contact(service_id, contact_block):
    letter_contacts = dao_get_letter_contacts_by_service_id(service_id)
    if len(letter_contacts) == 0:
        letter_contact = ServiceLetterContact(
            service_id=service_id,
            contact_block=contact_block
        )
        dao_create_letter_contact(letter_contact)
    elif len(letter_contacts) == 1:
        letter_contacts[0].contact_block = contact_block
        dao_update_letter_contact(letter_contacts[0])
    else:
        # Once we move allowing letter contact blocks, this method will be removed
        raise InvalidRequest(
            "Multiple letter contacts were found, this method should not be used.",
            status_code=500
        )


@transactional
def dao_create_letter_contact(letter_contact):
    db.session.add(letter_contact)


@transactional
def dao_update_letter_contact(letter_contact):
    db.session.add(letter_contact)
