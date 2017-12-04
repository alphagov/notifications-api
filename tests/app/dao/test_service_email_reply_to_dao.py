import uuid

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.dao.service_email_reply_to_dao import (
    dao_get_reply_to_by_service_id,
    add_reply_to_email_address_for_service, update_reply_to_email_address, dao_get_reply_to_by_id)
from app.errors import InvalidRequest
from app.models import ServiceEmailReplyTo
from tests.app.db import create_reply_to_email, create_service


def test_dao_get_reply_to_by_service_id(notify_db_session):
    service = create_service()
    default_reply_to = create_reply_to_email(service=service, email_address='something@email.com')
    second_reply_to = create_reply_to_email(service=service, email_address='second@email.com', is_default=False)
    another_reply_to = create_reply_to_email(service=service, email_address='another@email.com', is_default=False)

    results = dao_get_reply_to_by_service_id(service_id=service.id)

    assert len(results) == 3
    assert default_reply_to == results[0]
    assert another_reply_to == results[1]
    assert second_reply_to == results[2]


def test_add_reply_to_email_address_for_service_creates_first_email_for_service(notify_db_session):
    service = create_service()
    add_reply_to_email_address_for_service(service_id=service.id,
                                           email_address='new@address.com',
                                           is_default=True)

    results = dao_get_reply_to_by_service_id(service_id=service.id)
    assert len(results) == 1
    assert results[0].email_address == 'new@address.com'
    assert results[0].is_default


def test_add_reply_to_email_address_for_service_creates_another_email_for_service(notify_db_session):
    service = create_service()
    create_reply_to_email(service=service, email_address="first@address.com")

    add_reply_to_email_address_for_service(service_id=service.id, email_address='second@address.com', is_default=False)

    results = dao_get_reply_to_by_service_id(service_id=service.id)
    assert len(results) == 2
    for x in results:
        if x.email_address == 'first@address.com':
            assert x.is_default
        elif x.email_address == 'second@address.com':
            assert not x.is_default
        else:
            assert False


def test_add_reply_to_email_address_new_reply_to_is_default_existing_reply_to_is_not(notify_db_session):
    service = create_service()
    create_reply_to_email(service=service, email_address="first@address.com", is_default=True)
    add_reply_to_email_address_for_service(service_id=service.id, email_address='second@address.com', is_default=True)

    results = dao_get_reply_to_by_service_id(service_id=service.id)
    assert len(results) == 2
    for x in results:
        if x.email_address == 'first@address.com':
            assert not x.is_default
        elif x.email_address == 'second@address.com':
            assert x.is_default
        else:
            assert False


def test_add_reply_to_email_address_can_add_a_third_reply_to_address(sample_service):
    add_reply_to_email_address_for_service(service_id=sample_service.id,
                                           email_address="first@address.com",
                                           is_default=True)
    add_reply_to_email_address_for_service(service_id=sample_service.id, email_address='second@address.com',
                                           is_default=False)
    add_reply_to_email_address_for_service(service_id=sample_service.id, email_address='third@address.com',
                                           is_default=False)

    results = dao_get_reply_to_by_service_id(service_id=sample_service.id)
    assert len(results) == 3

    for x in results:
        if x.email_address == 'first@address.com':
            assert x.is_default
        elif x.email_address == 'second@address.com':
            assert not x.is_default
        elif x.email_address == 'third@address.com':
            assert not x.is_default
        else:
            assert False


def test_add_reply_to_email_address_ensures_first_reply_to_is_default(sample_service):
    with pytest.raises(expected_exception=InvalidRequest):
        add_reply_to_email_address_for_service(service_id=sample_service.id,
                                               email_address="first@address.com", is_default=False)


def test_add_reply_to_email_address_ensure_there_is_not_more_than_one_default(sample_service):
    create_reply_to_email(service=sample_service, email_address='first@email.com', is_default=True)
    create_reply_to_email(service=sample_service, email_address='second@email.com', is_default=True)
    with pytest.raises(Exception):
        add_reply_to_email_address_for_service(service_id=sample_service.id,
                                               email_address='third_email@address.com',
                                               is_default=False)


def test_update_reply_to_email_address(sample_service):
    first_reply_to = create_reply_to_email(service=sample_service, email_address="first@address.com")
    update_reply_to_email_address(service_id=sample_service.id, reply_to_id=first_reply_to.id,
                                  email_address='change_address@email.com',
                                  is_default=True)
    updated_reply_to = ServiceEmailReplyTo.query.get(first_reply_to.id)

    assert updated_reply_to.email_address == 'change_address@email.com'
    assert updated_reply_to.updated_at
    assert updated_reply_to.is_default


def test_update_reply_to_email_address_set_updated_to_default(sample_service):
    create_reply_to_email(service=sample_service, email_address="first@address.com")
    second_reply_to = create_reply_to_email(service=sample_service,
                                            email_address="second@address.com",
                                            is_default=False)

    update_reply_to_email_address(service_id=sample_service.id,
                                  reply_to_id=second_reply_to.id,
                                  email_address='change_address@email.com',
                                  is_default=True)

    results = ServiceEmailReplyTo.query.all()
    assert len(results) == 2
    for x in results:
        if x.email_address == 'change_address@email.com':
            assert x.is_default
        elif x.email_address == 'first@address.com':
            assert not x.is_default
        else:
            assert False


def test_update_reply_to_email_address_raises_exception_if_single_reply_to_and_setting_default_to_false(sample_service):
    first_reply_to = create_reply_to_email(service=sample_service, email_address="first@address.com")
    with pytest.raises(expected_exception=InvalidRequest):
        update_reply_to_email_address(service_id=sample_service.id,
                                      reply_to_id=first_reply_to.id,
                                      email_address='should@fail.com',
                                      is_default=False)


def test_dao_get_reply_to_by_id(sample_service):
    reply_to = create_reply_to_email(service=sample_service, email_address='email@address.com')
    result = dao_get_reply_to_by_id(service_id=sample_service.id, reply_to_id=reply_to.id)
    assert result == reply_to


def test_dao_get_reply_to_by_id_raises_sqlalchemy_error_when_reply_to_does_not_exist(sample_service):
    with pytest.raises(SQLAlchemyError):
        dao_get_reply_to_by_id(service_id=sample_service.id, reply_to_id=uuid.uuid4())


def test_dao_get_reply_to_by_id_raises_sqlalchemy_error_when_service_does_not_exist(sample_service):
    reply_to = create_reply_to_email(service=sample_service, email_address='email@address.com')
    with pytest.raises(SQLAlchemyError):
        dao_get_reply_to_by_id(service_id=uuid.uuid4(), reply_to_id=reply_to.id)
