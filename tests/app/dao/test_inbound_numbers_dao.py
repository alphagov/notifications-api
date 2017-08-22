import pytest
from sqlalchemy.exc import IntegrityError

from app.dao.inbound_numbers_dao import (
    dao_get_inbound_numbers,
    dao_get_inbound_number_for_service,
    dao_get_available_inbound_numbers,
    dao_set_inbound_number_to_service,
    dao_set_inbound_number_active_flag
)
from app.models import InboundNumber

from tests.app.db import create_service, create_inbound_number


def test_get_inbound_numbers(notify_db, notify_db_session, sample_inbound_numbers):
    res = dao_get_inbound_numbers()

    assert len(res) == len(sample_inbound_numbers)
    assert res == sample_inbound_numbers


def test_get_available_inbound_numbers(notify_db, notify_db_session):
    inbound_number = create_inbound_number(number='1')

    res = dao_get_available_inbound_numbers()

    assert len(res) == 1
    assert res[0] == inbound_number


def test_set_service_id_on_inbound_number(notify_db, notify_db_session, sample_inbound_numbers):
    service = create_service(service_name='test service')
    numbers = dao_get_available_inbound_numbers()

    dao_set_inbound_number_to_service(service.id, numbers[0])

    res = InboundNumber.query.filter(InboundNumber.service_id == service.id).all()

    assert len(res) == 1
    assert res[0].service_id == service.id


def test_after_setting_service_id_that_inbound_number_is_unavailable(
        notify_db, notify_db_session, sample_inbound_numbers):
    service = create_service(service_name='test service')
    numbers = dao_get_available_inbound_numbers()

    assert len(numbers) == 1

    dao_set_inbound_number_to_service(service.id, numbers[0])

    res = dao_get_available_inbound_numbers()

    assert len(res) == 0


def test_setting_a_service_twice_will_raise_an_error(notify_db, notify_db_session):
    create_inbound_number(number='1')
    create_inbound_number(number='2')
    service = create_service(service_name='test service')
    numbers = dao_get_available_inbound_numbers()

    dao_set_inbound_number_to_service(service.id, numbers[0])

    with pytest.raises(IntegrityError) as e:
        dao_set_inbound_number_to_service(service.id, numbers[1])

    assert 'duplicate key value violates unique constraint' in str(e.value)


@pytest.mark.parametrize("active", [True, False])
def test_set_inbound_number_active_flag(notify_db, notify_db_session, sample_service, active):
    inbound_number = create_inbound_number(number='1')
    dao_set_inbound_number_to_service(sample_service.id, inbound_number)

    dao_set_inbound_number_active_flag(sample_service.id, active=active)

    inbound_number = dao_get_inbound_number_for_service(sample_service.id)

    assert inbound_number.active is active
