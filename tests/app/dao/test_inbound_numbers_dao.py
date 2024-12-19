import pytest
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.constants import INBOUND_SMS_TYPE
from app.dao.inbound_numbers_dao import (
    archive_or_release_inbound_number_for_service,
    dao_allocate_number_for_service,
    dao_get_available_inbound_numbers,
    dao_get_inbound_number,
    dao_get_inbound_number_for_service,
    dao_get_inbound_numbers,
    dao_remove_inbound_sms_for_service,
    dao_set_inbound_number_active_flag,
    dao_set_inbound_number_to_service,
)
from app.dao.service_sms_sender_dao import dao_add_sms_sender_for_service, dao_get_sms_senders_by_service_id
from app.models import InboundNumber
from tests.app.db import create_inbound_number, create_service


def test_get_inbound_numbers(notify_db_session, sample_inbound_numbers):
    res = dao_get_inbound_numbers()

    assert len(res) == len(sample_inbound_numbers)
    assert res == sample_inbound_numbers


def test_get_available_inbound_numbers(notify_db_session):
    inbound_number = create_inbound_number(number="1")

    res = dao_get_available_inbound_numbers()

    assert len(res) == 1
    assert res[0] == inbound_number


def test_set_service_id_on_inbound_number(notify_db_session, sample_inbound_numbers):
    service = create_service(service_name="test service")
    numbers = dao_get_available_inbound_numbers()

    dao_set_inbound_number_to_service(service.id, numbers[0])

    res = InboundNumber.query.filter(InboundNumber.service_id == service.id).all()

    assert len(res) == 1
    assert res[0].service_id == service.id


def test_after_setting_service_id_that_inbound_number_is_unavailable(notify_db_session, sample_inbound_numbers):
    service = create_service(service_name="test service")
    numbers = dao_get_available_inbound_numbers()

    assert len(numbers) == 1

    dao_set_inbound_number_to_service(service.id, numbers[0])

    res = dao_get_available_inbound_numbers()

    assert len(res) == 0


def test_setting_a_service_twice_will_raise_an_error(notify_db_session):
    create_inbound_number(number="1")
    create_inbound_number(number="2")
    service = create_service(service_name="test service")
    numbers = dao_get_available_inbound_numbers()

    dao_set_inbound_number_to_service(service.id, numbers[0])

    with pytest.raises(IntegrityError) as e:
        dao_set_inbound_number_to_service(service.id, numbers[1])

    assert "duplicate key value violates unique constraint" in str(e.value)


@pytest.mark.parametrize("active", [True, False])
def test_set_inbound_number_active_flag(notify_db_session, sample_service, active):
    inbound_number = create_inbound_number(number="1")
    dao_set_inbound_number_to_service(sample_service.id, inbound_number)

    dao_set_inbound_number_active_flag(sample_service.id, active=active)

    inbound_number = dao_get_inbound_number_for_service(sample_service.id)

    assert inbound_number.active is active


def test_dao_allocate_number_for_service(notify_db_session):
    number = "078945612"
    inbound_number = create_inbound_number(number=number)
    service = create_service()

    updated_inbound_number = dao_allocate_number_for_service(service_id=service.id, inbound_number_id=inbound_number.id)
    assert service.get_inbound_number() == number
    assert updated_inbound_number.service_id == service.id


def test_dao_allocate_number_for_service_raises_if_inbound_number_already_taken(notify_db_session, sample_service):
    number = "078945612"
    inbound_number = create_inbound_number(number=number, service_id=sample_service.id)
    service = create_service(service_name="Service needs an inbound number")
    with pytest.raises(Exception) as exc:
        dao_allocate_number_for_service(service_id=service.id, inbound_number_id=inbound_number.id)
    assert "is not available" in str(exc.value)


def test_dao_allocate_number_for_service_raises_if_invalid_inbound_number(notify_db_session, fake_uuid):
    service = create_service(service_name="Service needs an inbound number")
    with pytest.raises(Exception) as exc:
        dao_allocate_number_for_service(service_id=service.id, inbound_number_id=fake_uuid)
    assert "is not available" in str(exc.value)


def test_archive_or_release_inbound_number_for_service_archive(sample_service, sample_inbound_numbers):
    inbound = next((inbound for inbound in sample_inbound_numbers if inbound.service_id == sample_service.id), None)

    archive_or_release_inbound_number_for_service(sample_service.id, True)

    updated_inbound = InboundNumber.query.filter_by(number=inbound.number).one_or_none()

    assert updated_inbound.service_id is None
    assert updated_inbound.active is False


def test_archive_or_release_inbound_number_for_service_release(sample_service, sample_inbound_numbers):
    inbound = next((inbound for inbound in sample_inbound_numbers if inbound.service_id == sample_service.id), None)

    archive_or_release_inbound_number_for_service(sample_service.id, False)

    updated_inbound = InboundNumber.query.filter_by(number=inbound.number).one_or_none()

    assert updated_inbound.service_id is None
    assert updated_inbound.active is True


@pytest.mark.parametrize(
    "archive, inbound_number, expected_active_status",
    [
        (True, "7654321", False),
        (False, "1234567", True),
    ],
)
def test_dao_remove_inbound_sms_for_service_success(
    admin_request, sample_service_full_permissions, archive, inbound_number, expected_active_status
):
    service = sample_service_full_permissions
    service_inbound = dao_get_inbound_number_for_service(service.id)
    dao_add_sms_sender_for_service(service.id, inbound_number, is_default=True, inbound_number_id=service_inbound.id)
    sms_senders = dao_get_sms_senders_by_service_id(service.id)

    assert (service.has_permission(INBOUND_SMS_TYPE)) is True
    assert any(x.inbound_number_id is not None and x.sms_sender == inbound_number for x in sms_senders) is True
    assert service_inbound.active is True
    assert service_inbound.service_id is not None

    dao_remove_inbound_sms_for_service(service.id, archive=archive)

    sms_senders = dao_get_sms_senders_by_service_id(service.id)
    updated_service_inbound = dao_get_inbound_number_for_service(service.id)
    inbound = dao_get_inbound_number(service_inbound.id)

    assert (service.has_permission(INBOUND_SMS_TYPE)) is False
    assert any(x.inbound_number_id is not None and x.sms_sender == inbound_number for x in sms_senders) is False
    assert updated_service_inbound is None
    assert inbound.service_id is None
    assert inbound.active is expected_active_status


def test_dao_remove_inbound_sms_for_service_failure(sample_service_full_permissions, mocker, notify_db_session):
    inbound_number = "76543953521"
    service = sample_service_full_permissions
    service_inbound = dao_get_inbound_number_for_service(service.id)
    dao_add_sms_sender_for_service(service.id, inbound_number, is_default=True, inbound_number_id=service_inbound.id)

    sms_senders = dao_get_sms_senders_by_service_id(service.id)
    assert service.has_permission(INBOUND_SMS_TYPE) is True
    assert any(x.inbound_number_id is not None and x.sms_sender == inbound_number for x in sms_senders) is True
    assert service_inbound.active is True
    assert service_inbound.service_id is not None

    with mocker.patch(
        "app.dao.inbound_numbers_dao.archive_or_release_inbound_number_for_service", side_effect=SQLAlchemyError
    ):
        with pytest.raises(SQLAlchemyError):
            dao_remove_inbound_sms_for_service(service.id, archive=True)

    sms_senders_after = dao_get_sms_senders_by_service_id(service.id)
    updated_service_inbound = dao_get_inbound_number_for_service(service.id)
    inbound = dao_get_inbound_number(service_inbound.id)

    assert service.has_permission(INBOUND_SMS_TYPE) is True
    assert any(x.inbound_number_id is not None and x.sms_sender == inbound_number for x in sms_senders_after) is True
    assert updated_service_inbound is not None
    assert inbound.service_id == service.id
    assert inbound.active is True
