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


def test_rest_set_inbound_number_active_flag_off(
        admin_request, notify_db_session):
    service = create_service(service_name='test service 1')
    inbound_number = create_inbound_number(
        number='1', provider='mmg', active=True, service_id=service.id)

    admin_request.post(
        'inbound_number.post_set_inbound_number_off',
        _expected_status=204,
        service_id=service.id
    )

    inbound_number_from_db = dao_get_inbound_number_for_service(service.id)
    assert not inbound_number_from_db.active


def test_get_available_inbound_numbers_returns_empty_list(admin_request):
    result = admin_request.get('inbound_number.get_available_inbound_numbers')

    assert result['data'] == []


def test_get_available_inbound_numbers(admin_request, sample_inbound_numbers):
    result = admin_request.get('inbound_number.get_available_inbound_numbers')

    assert len(result['data']) == 1
    assert result['data'] == [i.serialize() for i in sample_inbound_numbers if
                              i.service_id is None]
