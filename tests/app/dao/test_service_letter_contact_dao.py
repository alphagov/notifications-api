import pytest

from app.dao.service_letter_contact_dao import (
    add_letter_contact_for_service,
    create_or_update_letter_contact,
    dao_get_letter_contacts_by_service_id,
    update_letter_contact
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


def test_create_or_update_letter_contact_raises_exception_if_multiple_letter_contacts_exist(notify_db_session):
    service = create_service()
    create_letter_contact(service=service, contact_block='Edinburgh, ED1 1AA')
    create_letter_contact(service=service, contact_block='Manchester, MA1 2BB', is_default=False)

    with pytest.raises(expected_exception=InvalidRequest) as e:
        create_or_update_letter_contact(service_id=service.id, contact_block='Swansea, SN1 3CC')
    assert e.value.message == "Multiple letter contacts were found, this method should not be used."


def test_add_letter_contact_for_service_creates_additional_letter_contact_for_service(notify_db_session):
    service = create_service()

    create_letter_contact(service=service, contact_block='Edinburgh, ED1 1AA')
    add_letter_contact_for_service(service_id=service.id, contact_block='Swansea, SN1 3CC', is_default=False)

    results = dao_get_letter_contacts_by_service_id(service_id=service.id)

    assert len(results) == 2

    assert results[0].contact_block == 'Edinburgh, ED1 1AA'
    assert results[0].is_default

    assert results[1].contact_block == 'Swansea, SN1 3CC'
    assert not results[1].is_default


def test_add_another_letter_contact_as_default_overrides_existing(notify_db_session):
    service = create_service()

    create_letter_contact(service=service, contact_block='Edinburgh, ED1 1AA')
    add_letter_contact_for_service(service_id=service.id, contact_block='Swansea, SN1 3CC', is_default=True)

    results = dao_get_letter_contacts_by_service_id(service_id=service.id)

    assert len(results) == 2

    assert results[0].contact_block == 'Edinburgh, ED1 1AA'
    assert not results[0].is_default

    assert results[1].contact_block == 'Swansea, SN1 3CC'
    assert results[1].is_default


def test_add_letter_contact_does_not_override_default(notify_db_session):
    service = create_service()

    add_letter_contact_for_service(service_id=service.id, contact_block='Edinburgh, ED1 1AA', is_default=True)
    add_letter_contact_for_service(service_id=service.id, contact_block='Swansea, SN1 3CC', is_default=False)

    results = dao_get_letter_contacts_by_service_id(service_id=service.id)

    assert len(results) == 2

    assert results[0].contact_block == 'Edinburgh, ED1 1AA'
    assert results[0].is_default

    assert results[1].contact_block == 'Swansea, SN1 3CC'
    assert not results[1].is_default


def test_add_letter_contact_with_no_default_raises_exception(notify_db_session):
    service = create_service()
    with pytest.raises(expected_exception=InvalidRequest):
        add_letter_contact_for_service(
            service_id=service.id,
            contact_block='Swansea, SN1 3CC',
            is_default=False
        )


def test_add_letter_contact_when_multiple_defaults_exist_raises_exception(notify_db_session):
    service = create_service()
    create_letter_contact(service=service, contact_block='Edinburgh, ED1 1AA')
    create_letter_contact(service=service, contact_block='Aberdeen, AB12 23X')

    with pytest.raises(Exception):
        add_letter_contact_for_service(service_id=service.id, contact_block='Swansea, SN1 3CC', is_default=False)


def test_can_update_letter_contact(notify_db_session):
    service = create_service()
    letter_contact = create_letter_contact(service=service, contact_block='Aberdeen, AB12 23X')

    update_letter_contact(
        service_id=service.id,
        letter_contact_id=letter_contact.id,
        contact_block='Warwick, W14 TSR',
        is_default=True
    )

    updated_letter_contact = ServiceLetterContact.query.get(letter_contact.id)

    assert updated_letter_contact.contact_block == 'Warwick, W14 TSR'
    assert updated_letter_contact.updated_at
    assert updated_letter_contact.is_default


def test_update_letter_contact_as_default_overides_existing_default(notify_db_session):
    service = create_service()

    create_letter_contact(service=service, contact_block='Aberdeen, AB12 23X')
    second_letter_contact = create_letter_contact(service=service, contact_block='Swansea, SN1 3CC', is_default=False)

    update_letter_contact(
        service_id=service.id,
        letter_contact_id=second_letter_contact.id,
        contact_block='Warwick, W14 TSR',
        is_default=True
    )

    results = dao_get_letter_contacts_by_service_id(service_id=service.id)
    assert len(results) == 2

    assert results[0].contact_block == 'Aberdeen, AB12 23X'
    assert not results[0].is_default

    assert results[1].contact_block == 'Warwick, W14 TSR'
    assert results[1].is_default


def test_update_letter_contact_unset_default_for_only_letter_contact_raises_exception(notify_db_session):
    service = create_service()
    only_letter_contact = create_letter_contact(service=service, contact_block='Aberdeen, AB12 23X')

    with pytest.raises(expected_exception=InvalidRequest):
        update_letter_contact(
            service_id=service.id,
            letter_contact_id=only_letter_contact.id,
            contact_block='Warwick, W14 TSR',
            is_default=False
        )
