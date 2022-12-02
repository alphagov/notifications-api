import pytest

from app.dao.inbound_numbers_dao import (
    dao_get_available_inbound_numbers,
    dao_get_inbound_number_for_service,
)
from app.dao.service_sms_sender_dao import (
    dao_add_sms_sender_for_service,
    dao_get_sms_senders_by_service_id,
)
from tests.app.db import create_inbound_number, create_service


def test_rest_get_inbound_numbers_when_none_set_returns_empty_list(admin_request, notify_db_session):
    result = admin_request.get("inbound_number.get_inbound_numbers")

    assert result["data"] == []


def test_rest_get_inbound_numbers(admin_request, sample_inbound_numbers):
    result = admin_request.get("inbound_number.get_inbound_numbers")

    assert len(result["data"]) == len(sample_inbound_numbers)
    assert result["data"] == [i.serialize() for i in sample_inbound_numbers]


def test_rest_get_inbound_number(admin_request, sample_service):
    inbound_number = create_inbound_number(number="1", provider="mmg", active=False, service_id=sample_service.id)

    result = admin_request.get("inbound_number.get_inbound_number_for_service", service_id=sample_service.id)
    assert result["data"] == inbound_number.serialize()


def test_rest_get_inbound_number_when_service_is_not_assigned_returns_empty_dict(
    admin_request, notify_db_session, sample_service
):
    result = admin_request.get("inbound_number.get_inbound_number_for_service", service_id=sample_service.id)
    assert result["data"] == {}


def test_rest_set_inbound_number_active_flag_off(admin_request, notify_db_session):
    service = create_service(service_name="test service 1")
    create_inbound_number(number="1", provider="mmg", active=True, service_id=service.id)

    admin_request.post("inbound_number.post_set_inbound_number_off", _expected_status=204, service_id=service.id)

    inbound_number_from_db = dao_get_inbound_number_for_service(service.id)
    assert not inbound_number_from_db.active


def test_get_available_inbound_numbers_returns_empty_list(admin_request):
    result = admin_request.get("inbound_number.get_available_inbound_numbers")

    assert result["data"] == []


def test_get_available_inbound_numbers(admin_request, sample_inbound_numbers):
    result = admin_request.get("inbound_number.get_available_inbound_numbers")

    assert len(result["data"]) == 1
    assert result["data"] == [i.serialize() for i in sample_inbound_numbers if i.service_id is None]


@pytest.mark.parametrize("inbound_number_provided", [True, False])
def test_add_inbound_number_to_service_when_service_has_one_sms_sender(
    admin_request,
    sample_inbound_numbers,
    inbound_number_provided,
):
    service = create_service(service_name="new service")
    # There is one inbound number which is free to be assigned
    available_inbound_number = dao_get_available_inbound_numbers()[0]

    data = {"inbound_number_id": str(available_inbound_number.id)} if inbound_number_provided else {}

    admin_request.post(
        "inbound_number.add_inbound_number_to_service",
        service_id=service.id,
        _data=data,
        _expected_status=201,
    )

    assert service.inbound_number == available_inbound_number

    sms_senders = dao_get_sms_senders_by_service_id(service.id)
    assert len(sms_senders) == 1
    assert sms_senders[0].inbound_number == available_inbound_number


@pytest.mark.parametrize("inbound_number_provided", [True, False])
def test_add_inbound_number_to_service_when_service_has_multiple_senders(
    admin_request,
    sample_inbound_numbers,
    inbound_number_provided,
):
    service = create_service(service_name="new service")
    dao_add_sms_sender_for_service(service.id, "sender two", is_default=True)

    # There is one inbound number which is free to be assigned
    available_inbound_number = dao_get_available_inbound_numbers()[0]

    data = {"inbound_number_id": str(available_inbound_number.id)} if inbound_number_provided else {}

    admin_request.post(
        "inbound_number.add_inbound_number_to_service",
        service_id=service.id,
        _data=data,
        _expected_status=201,
    )

    assert service.inbound_number == available_inbound_number

    sms_senders = dao_get_sms_senders_by_service_id(service.id)
    assert len(sms_senders) == 3

    default_sender = [sender for sender in sms_senders if sender.is_default][0]
    assert default_sender.inbound_number == available_inbound_number


def test_add_inbound_number_to_service_when_no_number_is_provided_and_no_numbers_are_available(
    admin_request,
    sample_service,
):
    with pytest.raises(Exception) as exc:
        admin_request.post(
            "inbound_number.add_inbound_number_to_service",
            service_id=sample_service.id,
            _data={},
            _expected_status=500,
        )
    assert str(exc.value) == "There are no available inbound numbers"
