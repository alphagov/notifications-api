from flask import url_for
import json

from app.models import InboundNumber
from app.dao.inbound_numbers_dao import (
    dao_get_inbound_numbers,
    dao_get_inbound_number,
    dao_get_available_inbound_numbers,
    dao_get_inbound_number_for_service,
    dao_set_inbound_number_to_service
)

from tests.app.db import create_service, create_inbound_number


def test_rest_get_inbound_numbers(admin_request, sample_inbound_numbers):
    result = admin_request.get('inbound_number.get_inbound_numbers')

    assert len(result['data']) == len(sample_inbound_numbers)
    assert result['data'] == [i.serialize() for i in sample_inbound_numbers]


def test_rest_allocate_inbound_number(admin_request, notify_db_session, sample_inbound_numbers):
    service = create_service(service_name='test service')
    admin_request.post(
        'inbound_number.post_allocate_inbound_number',
        _expected_status=204,
        service_id=service.id
    )


def test_rest_allocate_inbound_number_when_no_inbound_available_returns_409(
        admin_request, notify_db_session, sample_service):
    service_1 = create_service(service_name='test service 1')
    create_inbound_number(number='4', provider='mmg', active=False, service_id=sample_service.id)
    create_inbound_number(number='5', provider='mmg', active=True, service_id=service_1.id)
    service_2 = create_service(service_name='test service 2')

    admin_request.post(
        'inbound_number.post_allocate_inbound_number',
        _expected_status=409,
        service_id=service_2.id
    )


def test_rest_set_service_to_several_inbound_numbers_returns_409(
        admin_request, notify_db_session, sample_service):
    service_1 = create_service(service_name='test service 1')
    create_inbound_number(number='4', provider='mmg', active=False, service_id=sample_service.id)
    inbound_number = create_inbound_number(number='5', provider='mmg', active=True, service_id=service_1.id)
    service_2 = create_service(service_name='test service 2')

    admin_request.post(
        'inbound_number.post_set_inbound_number_for_service',
        _expected_status=409,
        inbound_number_id=inbound_number.id,
        service_id=service_2.id
    )


def test_rest_set_number_to_several_services_returns_409(
        admin_request, notify_db_session, sample_service):
    service_1 = create_service(service_name='test service 1')
    inbound_number = create_inbound_number(number='4', provider='mmg', active=False, service_id=sample_service.id)
    service_2 = create_service(service_name='test service 2')

    admin_request.post(
        'inbound_number.post_set_inbound_number_for_service',
        _expected_status=409,
        inbound_number_id=inbound_number.id,
        service_id=service_2.id
    )


def test_rest_set_inbound_number_active_flag_off(admin_request, notify_db_session):
    service = create_service(service_name='test service 1')
    inbound_number = create_inbound_number(number='1', provider='mmg', active=True, service_id=service.id)

    admin_request.post(
        'inbound_number.post_set_inbound_number_off',
        _expected_status=204,
        inbound_number_id=inbound_number.id
    )

    inbound_number_off = dao_get_inbound_number(inbound_number.id)
    assert not inbound_number_off.active


def test_rest_set_inbound_number_active_flag_on(admin_request, notify_db_session):
    service = create_service(service_name='test service 1')
    inbound_number = create_inbound_number(number='1', provider='mmg', active=True, service_id=service.id)

    admin_request.post(
        'inbound_number.post_set_inbound_number_on',
        _expected_status=204,
        inbound_number_id=inbound_number.id
    )

    inbound_number_on = dao_get_inbound_number(inbound_number.id)
    assert inbound_number_on.active
