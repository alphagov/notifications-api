import uuid

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.dao.service_sms_sender_dao import (
    insert_or_update_service_sms_sender,
    dao_add_sms_sender_for_service,
    dao_update_service_sms_sender, dao_get_service_sms_senders_by_id, dao_get_sms_senders_by_service_id)
from app.models import ServiceSmsSender
from tests.app.db import create_service


def test_update_service_sms_sender_updates_existing_row(notify_db_session):
    service = create_service()
    insert_or_update_service_sms_sender(service, 'testing')
    service_sms_senders = ServiceSmsSender.query.filter_by(service_id=service.id).all()
    assert len(service_sms_senders) == 1
    assert service_sms_senders[0].sms_sender == service.sms_sender

    insert_or_update_service_sms_sender(service, 'NEW_SMS')

    updated_sms_senders = ServiceSmsSender.query.filter_by(service_id=service.id).all()
    assert len(updated_sms_senders) == 1
    assert updated_sms_senders[0].sms_sender == 'NEW_SMS'
    assert updated_sms_senders[0].is_default


def test_create_service_inserts_new_service_sms_sender(notify_db_session):
    assert ServiceSmsSender.query.count() == 0

    service = create_service(sms_sender='new_sms')
    insert_or_update_service_sms_sender(service, 'new_sms')
    service_sms_senders = ServiceSmsSender.query.all()
    assert len(service_sms_senders) == 1
    assert service_sms_senders[0].sms_sender == 'new_sms'
    assert service_sms_senders[0].is_default


def test_dao_get_service_sms_senders_id(notify_db_session):
    service = create_service(sms_sender='first_sms')
    second_sender = dao_add_sms_sender_for_service(service_id=service.id,
                                                   sms_sender='second',
                                                   is_default=False,
                                                   inbound_number_id=None)
    result = dao_get_service_sms_senders_by_id(service_id=service.id,
                                               service_sms_sender_id=second_sender.id)
    assert result.sms_sender == "second"
    assert not result.is_default


def test_dao_get_service_sms_senders_id_raise_exception_when_not_found(notify_db_session):
    service = create_service()
    with pytest.raises(expected_exception=SQLAlchemyError):
        dao_get_service_sms_senders_by_id(service_id=service.id,
                                          service_sms_sender_id=uuid.uuid4())


def test_dao_get_sms_senders_by_service_id(notify_db_session):
    service = create_service(sms_sender='first_sms')
    second_sender = dao_add_sms_sender_for_service(service_id=service.id,
                                                   sms_sender='second',
                                                   is_default=False,
                                                   inbound_number_id=None)
    results = dao_get_sms_senders_by_service_id(service_id=service.id)
    assert len(results) == 2
    for x in results:
        if x.is_default:
            x.sms_sender = 'first_sms'
        else:
            x == second_sender


def test_dao_add_sms_sender_for_service(notify_db_session):
    service = create_service(sms_sender="first_sms")
    new_sms_sender = dao_add_sms_sender_for_service(service_id=service.id,
                                                    sms_sender='new_sms',
                                                    is_default=False,
                                                    inbound_number_id=None)

    service_sms_senders = ServiceSmsSender.query.order_by(ServiceSmsSender.created_at).all()
    assert len(service_sms_senders) == 2
    assert service_sms_senders[0].sms_sender == 'first_sms'
    assert service_sms_senders[0].is_default
    assert service_sms_senders[1] == new_sms_sender


def test_dao_add_sms_sender_for_service_switches_default(notify_db_session):
    service = create_service(sms_sender="first_sms")
    new_sms_sender = dao_add_sms_sender_for_service(service_id=service.id,
                                                    sms_sender='new_sms',
                                                    is_default=True,
                                                    inbound_number_id=None)

    service_sms_senders = ServiceSmsSender.query.order_by(ServiceSmsSender.created_at).all()
    assert len(service_sms_senders) == 2
    assert service_sms_senders[0].sms_sender == 'first_sms'
    assert not service_sms_senders[0].is_default
    assert service_sms_senders[1] == new_sms_sender


def test_dao_update_service_sms_sender(notify_db_session):
    service = create_service(sms_sender='first_sms')
    service_sms_senders = ServiceSmsSender.query.filter_by(service_id=service.id).all()
    assert len(service_sms_senders) == 1
    sms_sender_to_update = service_sms_senders[0]

    dao_update_service_sms_sender(service_id=service.id,
                                  service_sms_sender_id=sms_sender_to_update.id,
                                  is_default=True,
                                  sms_sender="updated")
    sms_senders = ServiceSmsSender.query.filter_by(service_id=service.id).all()
    assert len(sms_senders) == 1
    assert sms_senders[0].is_default
    assert sms_senders[0].sms_sender == 'updated'
    assert not sms_senders[0].inbound_number_id


def test_dao_update_service_sms_sender_switches_default(notify_db_session):
    service = create_service(sms_sender='first_sms')
    sms_sender = dao_add_sms_sender_for_service(service_id=service.id,
                                                sms_sender='new_sms',
                                                is_default=False,
                                                inbound_number_id=None)
    dao_update_service_sms_sender(service_id=service.id,
                                  service_sms_sender_id=sms_sender.id,
                                  is_default=True,
                                  sms_sender="updated")
    sms_senders = ServiceSmsSender.query.filter_by(service_id=service.id).order_by(ServiceSmsSender.created_at).all()
    assert len(sms_senders) == 2
    assert sms_senders[0].sms_sender == 'first_sms'
    assert not sms_senders[0].is_default
    assert sms_senders[1].sms_sender == 'updated'
    assert sms_senders[1].is_default


def test_dao_update_service_sms_sender_raises_exception_when_no_default_after_update(notify_db_session):
    service = create_service(sms_sender='first_sms')
    sms_sender = dao_add_sms_sender_for_service(service_id=service.id,
                                                sms_sender='new_sms',
                                                is_default=True,
                                                inbound_number_id=None)
    with pytest.raises(expected_exception=Exception) as e:
        dao_update_service_sms_sender(service_id=service.id,
                                      service_sms_sender_id=sms_sender.id,
                                      is_default=False,
                                      sms_sender="updated")
