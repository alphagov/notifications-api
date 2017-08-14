import pytest

from flask import url_for
import json

from app.models import InboundNumber
from app.dao.inbound_numbers_dao import dao_get_inbound_number_for_service

from tests.app.db import create_service, create_inbound_number


def test_rest_get_inbound_numbers_when_none_set_returns_empty_list(admin_request):
    result = admin_request.get('inbound_number.get_inbound_numbers')

    assert result['data'] == []


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


def test_rest_get_inbound_number_when_service_is_not_assigned_returns_empty_dict(
        admin_request, notify_db_session, sample_service):
    result = admin_request.get(
        'inbound_number.get_inbound_number_for_service',
        service_id=sample_service.id
    )
    assert result['data'] == {}


def test_rest_allocate_inbound_number_to_service(
        admin_request, notify_db_session, sample_service):
    service = create_service(service_name='test service 1')
    inbound_number = create_inbound_number(number='1', provider='mmg', active=True)

    result = admin_request.post(
        'inbound_number.post_allocate_inbound_number',
        _expected_status=204,
        service_id=service.id
    )

    inbound_number_from_db = dao_get_inbound_number_for_service(service.id)

    assert inbound_number_from_db.active
    assert inbound_number_from_db.id == inbound_number.id
    assert inbound_number_from_db.number == inbound_number.number


def test_rest_allocate_inbound_number_to_service_raises_400_when_no_available_numbers(
        admin_request, notify_db_session, sample_service):
    service = create_service(service_name='test service 1')
    create_inbound_number(number='1', provider='mmg', active=False)

    result = admin_request.post(
        'inbound_number.post_allocate_inbound_number',
        _expected_status=400,
        service_id=service.id
    )

    assert result['message'] == 'No available inbound numbers'


def test_rest_allocate_inbound_number_to_service_sets_active_flag_true_when_flag_is_false(
        admin_request, notify_db_session, sample_service):
    service = create_service(service_name='test service 1')
    create_inbound_number(number='1', provider='mmg', active=False, service_id=service.id)

    result = admin_request.post(
        'inbound_number.post_allocate_inbound_number',
        _expected_status=204,
        service_id=service.id
    )

    inbound_number = dao_get_inbound_number_for_service(service.id)

    assert inbound_number.active


def test_rest_allocate_inbound_number_to_service_sets_active_flag_true_when_flag_is_true(
        admin_request, notify_db_session, sample_service):
    service = create_service(service_name='test service 1')
    create_inbound_number(number='1', provider='mmg', active=True, service_id=service.id)

    result = admin_request.post(
        'inbound_number.post_allocate_inbound_number',
        _expected_status=200,
        service_id=service.id
    )


def test_rest_set_inbound_number_active_flag_off(
        admin_request, notify_db_session):
    service = create_service(service_name='test service 1')
    inbound_number = create_inbound_number(
        number='1', provider='mmg', active=True, service_id=service.id)

    admin_request.post(
        'inbound_number.post_set_inbound_number_off',
        _expected_status=204,
        inbound_number_id=inbound_number.id
    )

    inbound_number_from_db = dao_get_inbound_number_for_service(service.id)
    assert not inbound_number_from_db.active
