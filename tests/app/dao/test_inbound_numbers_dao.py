import pytest

from app.dao.inbound_numbers_dao import (
    dao_get_inbound_numbers,
    dao_get_available_inbound_numbers,
    dao_get_inbound_number_for_service,
    dao_allocate_inbound_number_to_service
)
from app.models import InboundNumber

from tests.app.db import create_inbound_number, create_service


@pytest.fixture
def service_1(notify_db, notify_db_session):
    return create_service()


@pytest.fixture
def sample_inbound_numbers(notify_db, notify_db_session, service_1):
    inbound_numbers = []
    inbound_numbers.append(create_inbound_number(number='1', provider='mmg'))
    inbound_numbers.append(create_inbound_number(number='2', provider='mmg', active=False))
    inbound_numbers.append(create_inbound_number(number='3', provider='firetext', service_id=service_1.id))
    return inbound_numbers


def test_get_inbound_numbers(notify_db, notify_db_session, sample_inbound_numbers, service_1):
    res = dao_get_inbound_numbers()

    assert len(res) == 3
    assert res == sample_inbound_numbers


def test_get_available_inbound_numbers(notify_db, notify_db_session, sample_inbound_numbers):
    res = dao_get_available_inbound_numbers()

    assert len(res) == 1
    assert res[0] == sample_inbound_numbers[0]


def test_allocate_inbound_number_to_service(
        notify_db, notify_db_session, sample_inbound_numbers):
    service = create_service(service_name='test service')

    dao_allocate_inbound_number_to_service(service.id)

    res = InboundNumber.query.filter(InboundNumber.service_id == service.id).all()

    assert len(res) == 1
    assert res[0].service_id == service.id


def test_get_inbound_number_for_service(notify_db, notify_db_session, sample_inbound_numbers, service_1):
    res = dao_get_inbound_number_for_service(service_1.id)

    assert len(res) == 1
    assert res[0].number == '3'
    assert res[0].provider == 'firetext'
    assert res[0].service_id == service_1.id
