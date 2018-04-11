from sqlalchemy import desc

from app import db
from app.dao.dao_utils import transactional
from app.errors import InvalidRequest
from app.models import ServiceLetterContact


def dao_get_letter_contacts_by_service_id(service_id):
    letter_contacts = db.session.query(
        ServiceLetterContact
    ).filter(
        ServiceLetterContact.service_id == service_id,
        ServiceLetterContact.is_active == True  # noqa
    ).order_by(
        desc(ServiceLetterContact.is_default),
        desc(ServiceLetterContact.created_at)
    ).all()

    return letter_contacts


def dao_get_letter_contact_by_id(service_id, letter_contact_id):
    letter_contact = db.session.query(
        ServiceLetterContact
    ).filter(
        ServiceLetterContact.service_id == service_id,
        ServiceLetterContact.id == letter_contact_id,
        ServiceLetterContact.is_active == True  # noqa
    ).one()
    return letter_contact


@transactional
def add_letter_contact_for_service(service_id, contact_block, is_default):
    old_default = _get_existing_default(service_id)
    if is_default:
        _reset_old_default_to_false(old_default)
    else:
        _raise_when_no_default(old_default)

    new_letter_contact = ServiceLetterContact(
        service_id=service_id,
        contact_block=contact_block,
        is_default=is_default
    )
    db.session.add(new_letter_contact)
    return new_letter_contact


@transactional
def update_letter_contact(service_id, letter_contact_id, contact_block, is_default):
    old_default = _get_existing_default(service_id)
    # if we want to make this the default, ensure there are no other existing defaults
    if is_default:
        _reset_old_default_to_false(old_default)
    else:
        if old_default.id == letter_contact_id:
            raise InvalidRequest("You must have at least one letter contact as the default.", 400)

    letter_contact_update = ServiceLetterContact.query.get(letter_contact_id)
    letter_contact_update.contact_block = contact_block
    letter_contact_update.is_default = is_default
    db.session.add(letter_contact_update)
    return letter_contact_update


def _get_existing_default(service_id):
    letter_contacts = dao_get_letter_contacts_by_service_id(service_id=service_id)
    if letter_contacts:
        old_default = [x for x in letter_contacts if x.is_default]
        if len(old_default) == 1:
            return old_default[0]
        else:
            raise Exception(
                "There should only be one default letter contact for each service. Service {} has {}".format(
                    service_id,
                    len(old_default)
                )
            )
    return None


def _reset_old_default_to_false(old_default):
    if old_default:
        old_default.is_default = False
        db.session.add(old_default)


def _raise_when_no_default(old_default):
    # check that the update is not updating the only default to false
    if not old_default:
        raise InvalidRequest("You must have at least one letter contact as the default.", 400)
