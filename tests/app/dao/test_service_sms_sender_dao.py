import uuid

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.dao.service_sms_sender_dao import (
    dao_add_sms_sender_for_service,
    dao_update_service_sms_sender,
    dao_get_service_sms_senders_by_id,
    dao_get_sms_senders_by_service_id,
    update_existing_sms_sender_with_inbound_number)
from app.models import ServiceSmsSender
from tests.app.db import create_service, create_inbound_number


def test_dao_get_service_sms_senders_id(notify_db_session):
    service = create_service()
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
    service = create_service()
    second_sender = dao_add_sms_sender_for_service(service_id=service.id,
                                                   sms_sender='second',
                                                   is_default=False,
                                                   inbound_number_id=None)
    results = dao_get_sms_senders_by_service_id(service_id=service.id)
    assert len(results) == 2
    for x in results:
        if x.is_default:
            assert x.sms_sender == 'testing'
        else:
            assert x == second_sender


def test_dao_add_sms_sender_for_service(notify_db_session):
    service = create_service()
    new_sms_sender = dao_add_sms_sender_for_service(service_id=service.id,
                                                    sms_sender='new_sms',
                                                    is_default=False,
                                                    inbound_number_id=None)

    service_sms_senders = ServiceSmsSender.query.order_by(ServiceSmsSender.created_at).all()
    assert len(service_sms_senders) == 2
    assert service_sms_senders[0].sms_sender == 'testing'
    assert service_sms_senders[0].is_default
    assert not service_sms_senders[0].archived
    assert service_sms_senders[1] == new_sms_sender


def test_dao_add_sms_sender_for_service_switches_default(notify_db_session):
    service = create_service()
    new_sms_sender = dao_add_sms_sender_for_service(service_id=service.id,
                                                    sms_sender='new_sms',
                                                    is_default=True,
                                                    inbound_number_id=None)

    service_sms_senders = ServiceSmsSender.query.order_by(ServiceSmsSender.created_at).all()
    assert len(service_sms_senders) == 2
    assert service_sms_senders[0].sms_sender == 'testing'
    assert not service_sms_senders[0].is_default
    assert service_sms_senders[1] == new_sms_sender


def test_dao_update_service_sms_sender(notify_db_session):
    service = create_service()
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
    service = create_service()
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
    assert sms_senders[0].sms_sender == 'testing'
    assert not sms_senders[0].is_default
    assert sms_senders[1].sms_sender == 'updated'
    assert sms_senders[1].is_default


def test_dao_update_service_sms_sender_raises_exception_when_no_default_after_update(notify_db_session):
    service = create_service()
    sms_sender = dao_add_sms_sender_for_service(service_id=service.id,
                                                sms_sender='new_sms',
                                                is_default=True,
                                                inbound_number_id=None)
    with pytest.raises(expected_exception=Exception) as e:
        dao_update_service_sms_sender(service_id=service.id,
                                      service_sms_sender_id=sms_sender.id,
                                      is_default=False,
                                      sms_sender="updated")
    assert 'You must have at least one SMS sender as the default' in str(e.value)


def test_update_existing_sms_sender_with_inbound_number(notify_db_session):
    service = create_service()
    inbound_number = create_inbound_number(number='12345', service_id=service.id)

    existing_sms_sender = ServiceSmsSender.query.filter_by(service_id=service.id).one()
    sms_sender = update_existing_sms_sender_with_inbound_number(
        service_sms_sender=existing_sms_sender, sms_sender=inbound_number.number, inbound_number_id=inbound_number.id)

    assert sms_sender.inbound_number_id == inbound_number.id
    assert sms_sender.sms_sender == inbound_number.number
    assert sms_sender.is_default


def test_update_existing_sms_sender_with_inbound_number_raises_exception_if_inbound_number_does_not_exist(
        notify_db_session
):
    service = create_service()
    existing_sms_sender = ServiceSmsSender.query.filter_by(service_id=service.id).one()
    with pytest.raises(expected_exception=SQLAlchemyError):
        update_existing_sms_sender_with_inbound_number(service_sms_sender=existing_sms_sender,
                                                       sms_sender='blah',
                                                       inbound_number_id=uuid.uuid4())
