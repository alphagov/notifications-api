import pytest

from app.dao.service_letter_contact_dao import (
    create_or_update_letter_contact,
    dao_get_letter_contacts_by_service_id,
)
from app.errors import InvalidRequest
from app.models import ServiceLetterContact
from tests.app.db import create_letter_contact, create_service


def test_dao_get_letter_contacts_by_service_id(notify_db_session):
    service = create_service()
    default_letter_contact = create_letter_contact(service=service, contact_block='Edinburgh, ED1 1AA')
    another_letter_contact = create_letter_contact(service=service, contact_block='Cardiff, CA1 2DB')

    results = dao_get_letter_contacts_by_service_id(service_id=service.id)

    assert len(results) == 2
    assert default_letter_contact in results
    assert another_letter_contact in results


def test_create_or_update_letter_contact_creates_new_entry(notify_db_session):
    service = create_service()

    create_or_update_letter_contact(service.id, 'Cardiff, CA1 2DB')

    letter_contacts = dao_get_letter_contacts_by_service_id(service.id)

    assert ServiceLetterContact.query.count() == 1
    assert letter_contacts[0].service.id == service.id
    assert letter_contacts[0].contact_block == 'Cardiff, CA1 2DB'


def test_create_or_update_letter_contact_does_not_create_another_entry(notify_db_session):
    service = create_service()
    create_letter_contact(service, 'London, NW1 2DB')
    create_or_update_letter_contact(service.id, 'Bristol, BR1 2DB')

    letter_contacts = dao_get_letter_contacts_by_service_id(service.id)

    assert len(letter_contacts) == 1


def test_create_or_update_letter_contact_updates_existing_entry(notify_db_session):
    service = create_service()
    create_letter_contact(service, 'London, NW1 2DB')

    create_or_update_letter_contact(service.id, 'Bristol, BR1 2DB')

    letter_contact = dao_get_letter_contacts_by_service_id(service.id)

    assert len(letter_contact) == 1
    assert letter_contact[0].service.id == service.id
    assert letter_contact[0].contact_block == 'Bristol, BR1 2DB'


def test_create_or_update_letter_contact_raises_exception_if_multiple_contact_blocks_exist(notify_db_session):
    service = create_service()
    create_letter_contact(service=service, contact_block='Edinburgh, ED1 1AA')
    create_letter_contact(service=service, contact_block='Manchester, MA1 2BB', is_default=False)

    with pytest.raises(expected_exception=InvalidRequest) as e:
        create_or_update_letter_contact(service_id=service.id, contact_block='Swansea, SN1 3CC')
    assert e.value.message == "Multiple letter contacts were found, this method should not be used."
