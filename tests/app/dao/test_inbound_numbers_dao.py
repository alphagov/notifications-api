import pytest

from app.dao.inbound_numbers_dao import (
    dao_get_inbound_numbers,
    dao_get_available_inbound_numbers,
    dao_get_inbound_number_for_service,
    dao_allocate_inbound_number_to_service
)
from app.models import InboundNumber

from tests.app.db import create_service


def test_get_inbound_numbers(notify_db, notify_db_session, sample_inbound_numbers):
    res = dao_get_inbound_numbers()

    assert len(res) == 3
    assert res == sample_inbound_numbers


def test_get_available_inbound_numbers(notify_db, notify_db_session, sample_inbound_numbers):
    res = dao_get_available_inbound_numbers()

    assert len(res) == 1
    assert res[0] == sample_inbound_numbers[0]


def test_allocate_inbound_number_to_service(notify_db, notify_db_session, sample_inbound_numbers):
    service = create_service(service_name='test service')

    dao_allocate_inbound_number_to_service(service.id)

    res = InboundNumber.query.filter(InboundNumber.service_id == service.id).all()

    assert len(res) == 1
    assert res[0].service_id == service.id


def test_allocating_a_service_twice_will_raise_an_error(notify_db, notify_db_session, sample_inbound_numbers):
    service = create_service(service_name='test service')

    dao_allocate_inbound_number_to_service(service.id)

    with pytest.raises(IndexError) as e:
        dao_allocate_inbound_number_to_service(service.id)

    res = InboundNumber.query.filter(InboundNumber.service_id == service.id).all()

    assert len(res) == 1
    assert res[0].service_id == service.id
    assert str(e.value) == 'No inbound numbers available'


def test_get_inbound_number_for_service(notify_db, notify_db_session, sample_inbound_numbers, sample_service):
    res = dao_get_inbound_number_for_service(sample_service.id)

    assert len(res) == 1
    assert res[0].service_id == sample_service.id
