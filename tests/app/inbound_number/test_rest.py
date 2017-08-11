import pytest

from flask import url_for
import json

from app.models import InboundNumber
from app.dao.inbound_numbers_dao import (
    dao_get_inbound_numbers,
    dao_get_available_inbound_numbers,
    dao_get_inbound_number_for_service,
    dao_set_inbound_number_to_service
)

from tests.app.db import create_service, create_inbound_number


def test_rest_get_inbound_numbers(admin_request, sample_inbound_numbers):
    result = admin_request.get('inbound_number.get_inbound_numbers')

    assert len(result['data']) == len(sample_inbound_numbers)
    assert result['data'] == [i.serialize() for i in sample_inbound_numbers]


def test_rest_get_inbound_number(admin_request, notify_db_session, sample_service):
    inbound_number = create_inbound_number(number='1', provider='mmg', active=False, service_id=sample_service.id)

    result = admin_request.get(
        'inbound_number.get_inbound_number_for_service',
        service_id=sample_service.id
    )
    assert result['data'] == inbound_number.serialize()


def test_rest_set_number_to_several_services_returns_400(
        admin_request, notify_db_session, sample_service):
    service_1 = create_service(service_name='test service 1')
    inbound_number = create_inbound_number(number='1', provider='mmg', active=True, service_id=sample_service.id)
    create_inbound_number(number='2', provider='mmg', active=True, service_id=None)
    service_2 = create_service(service_name='test service 2')

    result = admin_request.post(
        'inbound_number.post_set_inbound_number_for_service',
        _expected_status=400,
        inbound_number_id=inbound_number.id,
        service_id=service_2.id
    )
    assert result['message'] == 'Inbound number already assigned'


def test_rest_set_multiple_numbers_to_a_service_returns_400(
        admin_request, notify_db_session, sample_service):
    create_inbound_number(number='1', provider='mmg', active=True, service_id=sample_service.id)
    inbound_number = create_inbound_number(number='2', provider='mmg', active=True, service_id=None)

    result = admin_request.post(
        'inbound_number.post_set_inbound_number_for_service',
        _expected_status=400,
        inbound_number_id=inbound_number.id,
        service_id=sample_service.id
    )
    assert result['message'] == 'Service already has an inbound number'


@pytest.mark.parametrize("active_flag,expected_flag_state", [("on", True), ("off", False)])
def test_rest_set_inbound_number_active_flag(
        admin_request, notify_db_session, active_flag, expected_flag_state):
    service = create_service(service_name='test service 1')
    inbound_number = create_inbound_number(
        number='1', provider='mmg', active=not expected_flag_state, service_id=service.id)

    admin_request.post(
        'inbound_number.post_set_inbound_number_{}'.format(active_flag),
        _expected_status=204,
        inbound_number_id=inbound_number.id
    )

    inbound_number_from_db = dao_get_inbound_number_for_service(service.id)
    assert inbound_number_from_db.active == expected_flag_state
