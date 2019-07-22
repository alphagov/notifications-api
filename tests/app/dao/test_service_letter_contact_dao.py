import uuid
import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.dao.service_letter_contact_dao import (
    add_letter_contact_for_service,
    archive_letter_contact,
    dao_get_letter_contacts_by_service_id,
    dao_get_letter_contact_by_id,
    update_letter_contact
)
from app.models import ServiceLetterContact
from tests.app.db import create_letter_contact, create_service, create_template


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


def test_dao_get_letter_contacts_by_service_id_does_not_return_archived_contacts(notify_db_session):
    service = create_service()
    create_letter_contact(service=service, contact_block='Edinburgh, ED1 1AA')
    create_letter_contact(service=service, contact_block='Cardiff, CA1 2DB', is_default=False)
    archived_contact = create_letter_contact(
        service=service,
        contact_block='London, E1 8QS',
        is_default=False,
        archived=True
    )

    results = dao_get_letter_contacts_by_service_id(service_id=service.id)

    assert len(results) == 2
    assert archived_contact not in results


def test_add_letter_contact_for_service_creates_additional_letter_contact_for_service(notify_db_session):
    service = create_service()

    create_letter_contact(service=service, contact_block='Edinburgh, ED1 1AA')
    add_letter_contact_for_service(service_id=service.id, contact_block='Swansea, SN1 3CC', is_default=False)

    results = dao_get_letter_contacts_by_service_id(service_id=service.id)

    assert len(results) == 2

    assert results[0].contact_block == 'Edinburgh, ED1 1AA'
    assert results[0].is_default
    assert not results[0].archived

    assert results[1].contact_block == 'Swansea, SN1 3CC'
    assert not results[1].is_default
    assert not results[1].archived


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


def test_add_letter_contact_with_no_default_is_fine(notify_db_session):
    service = create_service()
    letter_contact = add_letter_contact_for_service(
        service_id=service.id,
        contact_block='Swansea, SN1 3CC',
        is_default=False
    )
    assert service.letter_contacts == [letter_contact]


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


def test_update_letter_contact_unset_default_for_only_letter_contact_is_fine(notify_db_session):
    service = create_service()
    only_letter_contact = create_letter_contact(service=service, contact_block='Aberdeen, AB12 23X')
    update_letter_contact(
        service_id=service.id,
        letter_contact_id=only_letter_contact.id,
        contact_block='Warwick, W14 TSR',
        is_default=False
    )
    assert only_letter_contact.is_default is False


def test_archive_letter_contact(notify_db_session):
    service = create_service()
    create_letter_contact(service=service, contact_block='Aberdeen, AB12 23X')
    letter_contact = create_letter_contact(service=service, contact_block='Edinburgh, ED1 1AA', is_default=False)

    archive_letter_contact(service.id, letter_contact.id)

    assert letter_contact.archived
    assert letter_contact.updated_at is not None


def test_archive_letter_contact_does_not_archive_a_letter_contact_for_a_different_service(
    notify_db_session,
    sample_service,
):
    service = create_service(service_name="First service")
    letter_contact = create_letter_contact(
        service=sample_service,
        contact_block='Edinburgh, ED1 1AA',
        is_default=False)

    with pytest.raises(SQLAlchemyError):
        archive_letter_contact(service.id, letter_contact.id)

    assert not letter_contact.archived


def test_archive_letter_contact_can_archive_a_service_default_letter_contact(notify_db_session):
    service = create_service()
    letter_contact = create_letter_contact(service=service, contact_block='Edinburgh, ED1 1AA')
    archive_letter_contact(service.id, letter_contact.id)
    assert letter_contact.archived is True


def test_archive_letter_contact_does_dissociates_template_defaults_before_archiving(notify_db_session):
    service = create_service()
    create_letter_contact(service=service, contact_block='Edinburgh, ED1 1AA')
    template_default = create_letter_contact(service=service, contact_block='Aberdeen, AB12 23X', is_default=False)
    associated_template_1 = create_template(service=service, template_type='letter', reply_to=template_default.id)
    associated_template_2 = create_template(service=service, template_type='letter', reply_to=template_default.id)

    assert associated_template_1.reply_to == template_default.id
    assert associated_template_2.reply_to == template_default.id
    assert template_default.archived is False

    archive_letter_contact(service.id, template_default.id)

    assert associated_template_1.reply_to is None
    assert associated_template_2.reply_to is None
    assert template_default.archived is True


def test_dao_get_letter_contact_by_id(sample_service):
    letter_contact = create_letter_contact(service=sample_service, contact_block='Aberdeen, AB12 23X')
    result = dao_get_letter_contact_by_id(service_id=sample_service.id, letter_contact_id=letter_contact.id)
    assert result == letter_contact


def test_dao_get_letter_contact_by_id_raises_sqlalchemy_error_when_letter_contact_does_not_exist(sample_service):
    with pytest.raises(SQLAlchemyError):
        dao_get_letter_contact_by_id(service_id=sample_service.id, letter_contact_id=uuid.uuid4())


def test_dao_get_letter_contact_by_id_raises_sqlalchemy_error_when_letter_contact_is_archived(sample_service):
    archived_contact = create_letter_contact(
        service=sample_service,
        contact_block='Aberdeen, AB12 23X',
        archived=True)
    with pytest.raises(SQLAlchemyError):
        dao_get_letter_contact_by_id(service_id=sample_service.id, letter_contact_id=archived_contact.id)


def test_dao_get_letter_contact_by_id_raises_sqlalchemy_error_when_service_does_not_exist(sample_service):
    letter_contact = create_letter_contact(service=sample_service, contact_block='Some address')
    with pytest.raises(SQLAlchemyError):
        dao_get_letter_contact_by_id(service_id=uuid.uuid4(), letter_contact_id=letter_contact.id)
