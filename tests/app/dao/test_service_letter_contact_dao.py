import uuid
import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.dao.service_letter_contact_dao import (
    add_letter_contact_for_service,
    dao_get_letter_contacts_by_service_id,
    dao_get_letter_contact_by_id,
    update_letter_contact
)
from app.errors import InvalidRequest
from app.models import ServiceLetterContact
from tests.app.db import create_letter_contact, create_service


def test_dao_get_letter_contacts_by_service_id(notify_db_session):
    service = create_service()
    default_letter_contact = create_letter_contact(service=service, contact_block='Edinburgh, ED1 1AA')
    second_letter_contact = create_letter_contact(service=service, contact_block='Cardiff, CA1 2DB', is_default=False)
    third_letter_contact = create_letter_contact(service=service, contact_block='London, E1 8QS', is_default=False)

    results = dao_get_letter_contacts_by_service_id(service_id=service.id)

    assert len(results) == 3
    assert default_letter_contact == results[0]
    assert third_letter_contact == results[1]
    assert second_letter_contact == results[2]


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

    assert results[0].contact_block == 'Swansea, SN1 3CC'
    assert results[0].is_default

    assert results[1].contact_block == 'Edinburgh, ED1 1AA'
    assert not results[1].is_default


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

    assert results[0].contact_block == 'Warwick, W14 TSR'
    assert results[0].is_default

    assert results[1].contact_block == 'Aberdeen, AB12 23X'
    assert not results[1].is_default


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


def test_dao_get_letter_contact_by_id(sample_service):
    letter_contact = create_letter_contact(service=sample_service, contact_block='Aberdeen, AB12 23X')
    result = dao_get_letter_contact_by_id(service_id=sample_service.id, letter_contact_id=letter_contact.id)
    assert result == letter_contact


def test_dao_get_letter_contact_by_id_raises_sqlalchemy_error_when_letter_contact_does_not_exist(sample_service):
    with pytest.raises(SQLAlchemyError):
        dao_get_letter_contact_by_id(service_id=sample_service.id, letter_contact_id=uuid.uuid4())


def test_dao_get_letter_contact_by_id_raises_sqlalchemy_error_when_service_does_not_exist(sample_service):
    letter_contact = create_letter_contact(service=sample_service, contact_block='Some address')
    with pytest.raises(SQLAlchemyError):
        dao_get_letter_contact_by_id(service_id=uuid.uuid4(), letter_contact_id=letter_contact.id)
