import pytest

from app.dao.service_permissions_dao import (
    dao_fetch_service_permissions, dao_remove_service_permission)
from app.models import (
    EMAIL_TYPE, SMS_TYPE, LETTER_TYPE, INTERNATIONAL_SMS_TYPE, INCOMING_SMS_TYPE, SERVICE_PERMISSION_TYPES)

from tests.app.db import create_service_permissions, create_service


def test_create_service_permissions(sample_service):
    service_permission_types = [SMS_TYPE, INTERNATIONAL_SMS_TYPE]

    service_permissions = create_service_permissions(
        service_id=sample_service.id, permissions=service_permission_types)

    assert len(service_permissions) == len(service_permission_types)
    assert all(sp.service_id == sample_service.id for sp in service_permissions)
    assert all(sp.permission in service_permission_types for sp in service_permissions)


def test_fetch_service_permissions_gets_service_permissions(sample_service):
    service_permission_types = [LETTER_TYPE, EMAIL_TYPE, SMS_TYPE]
    create_service_permissions(service_id=sample_service.id, permissions=service_permission_types)
    service_permissions = dao_fetch_service_permissions(sample_service.id)

    assert len(service_permission_types) == len(service_permission_types)
    assert all(sp.service_id == sample_service.id for sp in service_permissions)
    assert all(sp.permission in service_permission_types for sp in service_permissions)


def test_add_service_permissions_to_existing_permissions(sample_service):
    service_permission_types_1 = [EMAIL_TYPE, INCOMING_SMS_TYPE]
    service_permission_types_2 = [LETTER_TYPE, INTERNATIONAL_SMS_TYPE, SMS_TYPE]

    create_service_permissions(
        service_id=sample_service.id, permissions=service_permission_types_1)
    create_service_permissions(
        service_id=sample_service.id, permissions=service_permission_types_2)

    permissions = dao_fetch_service_permissions(sample_service.id)

    assert len(permissions) == len(service_permission_types_1 + service_permission_types_2)


def test_create_invalid_service_permissions_raises_error(sample_service):
    service_permission_types = ['invalid']

    with pytest.raises(ValueError) as e:
        service_permissions = create_service_permissions(
            service_id=sample_service.id, permissions=service_permission_types)

    assert "'invalid' not of service permission type: " + str(SERVICE_PERMISSION_TYPES) in str(e.value)


def test_remove_service_permission(sample_service):
    service_permission_types = [EMAIL_TYPE, INCOMING_SMS_TYPE]
    service_permission_type_to_remove = EMAIL_TYPE
    service_permission_type_remaining = INCOMING_SMS_TYPE

    service_permissions = create_service_permissions(
        service_id=sample_service.id, permissions=service_permission_types)

    dao_remove_service_permission(sample_service.id, service_permission_type_to_remove)

    permissions = dao_fetch_service_permissions(sample_service.id)
    assert len(permissions) == 1
    assert permissions[0].permission == service_permission_type_remaining
    assert permissions[0].service_id == sample_service.id


def test_adding_duplicate_service_id_permission_raises_value_error(sample_service):
    service_permission_types = [EMAIL_TYPE, INCOMING_SMS_TYPE]
    service_permission_types_with_duplicate_email_type = [LETTER_TYPE, EMAIL_TYPE]

    with pytest.raises(ValueError) as e:
        create_service_permissions(
            service_id=sample_service.id, permissions=service_permission_types)
        create_service_permissions(
            service_id=sample_service.id, permissions=service_permission_types_with_duplicate_email_type)

    assert "duplicate key value violates unique constraint \"service_permissions_pkey\"" in str(e.value)
