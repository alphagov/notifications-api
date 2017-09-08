from app.dao.service_email_reply_to_dao import (
    create_or_update_email_reply_to,
    dao_get_reply_to_by_service_id
)
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

    assert reply_to.service.id == service.id
    assert reply_to.email_address == 'different@mail.com'


def test_create_or_update_email_reply_to_creates_new_entry(notify_db_session):
    service = create_service()

    create_or_update_email_reply_to(service.id, 'test@mail.com')

    reply_to = dao_get_reply_to_by_service_id(service.id)

    assert ServiceEmailReplyTo.query.count() == 1
    assert reply_to.service.id == service.id
    assert reply_to.email_address == 'test@mail.com'
