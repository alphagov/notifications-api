import pytest

from app.dao.service_email_reply_to_dao import (
    create_or_update_email_reply_to,
    dao_get_reply_to_by_service_id
)
from app.errors import InvalidRequest
from app.models import ServiceEmailReplyTo
from tests.app.db import create_reply_to_email, create_service


def test_create_or_update_email_reply_to_does_not_create_another_entry(notify_db_session):
    service = create_service()
    create_reply_to_email(service, 'test@mail.com')

    create_or_update_email_reply_to(service.id, 'different@mail.com')

    reply_to = dao_get_reply_to_by_service_id(service.id)

    assert ServiceEmailReplyTo.query.count() == 1


def test_create_or_update_email_reply_to_updates_existing_entry(notify_db_session):
    service = create_service()
    create_reply_to_email(service, 'test@mail.com')

    create_or_update_email_reply_to(service.id, 'different@mail.com')

    reply_to = dao_get_reply_to_by_service_id(service.id)

    assert len(reply_to) == 1
    assert reply_to[0].service.id == service.id
    assert reply_to[0].email_address == 'different@mail.com'


def test_create_or_update_email_reply_to_creates_new_entry(notify_db_session):
    service = create_service()

    create_or_update_email_reply_to(service.id, 'test@mail.com')

    reply_to = dao_get_reply_to_by_service_id(service.id)

    assert ServiceEmailReplyTo.query.count() == 1
    assert reply_to[0].service.id == service.id
    assert reply_to[0].email_address == 'test@mail.com'


def test_create_or_update_email_reply_to_raises_exception_if_multilple_email_addresses_exist(notify_db_session):
    service = create_service()
    create_reply_to_email(service=service, email_address='something@email.com')
    create_reply_to_email(service=service, email_address='another@email.com', is_default=False)

    with pytest.raises(expected_exception=InvalidRequest) as e:
        create_or_update_email_reply_to(service_id=service.id, email_address='third@email.com')
    assert e.value.message == "Multiple reply to email addresses were found, this method should not be used."


def test_dao_get_reply_to_by_service_id(notify_db_session):
    service = create_service()
    default_reply_to = create_reply_to_email(service=service, email_address='something@email.com')
    another_reply_to = create_reply_to_email(service=service, email_address='another@email.com', is_default=False)

    results = dao_get_reply_to_by_service_id(service_id=service.id)

    assert len(results) == 2
    assert default_reply_to in results
    assert another_reply_to in results
