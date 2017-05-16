import pytest

from app.dao.service_permissions_dao import (
    dao_fetch_service_permissions, dao_remove_service_permission)
from app.models import (
    EMAIL_TYPE, SMS_TYPE, LETTER_TYPE, INTERNATIONAL_SMS_TYPE, INCOMING_SMS_TYPE, SERVICE_PERMISSION_TYPES)

from tests.app.db import create_service_permission, create_service


def test_create_service_permission(sample_service):
    service_permission_type = SMS_TYPE

    service_permission = create_service_permission(
        service_id=sample_service.id, permission=service_permission_type)

    assert len(service_permission) == 1
    assert all(sp.service_id == sample_service.id for sp in service_permission)
    assert all(sp.permission in service_permission_type for sp in service_permission)


def test_fetch_service_permissions_gets_service_permissions(sample_service):
    service_permission_types = [LETTER_TYPE, EMAIL_TYPE, SMS_TYPE]
    for spt in service_permission_types:
        create_service_permission(service_id=sample_service.id, permission=spt)
    service_permissions = dao_fetch_service_permissions(sample_service.id)

    assert len(service_permissions) == len(service_permission_types)
    assert all(sp.service_id == sample_service.id for sp in service_permissions)
    assert all(sp.permission in service_permission_types for sp in service_permissions)


def test_create_invalid_service_permissions_raises_error(sample_service):
    service_permission_type = 'invalid'

    with pytest.raises(ValueError) as e:
        create_service_permission(service_id=sample_service.id, permission=service_permission_type)

    assert "'invalid' not of service permission type: {}".format(str(SERVICE_PERMISSION_TYPES)) in str(e.value)


def test_remove_service_permission(sample_service):
    service_permission_types_to_create = [EMAIL_TYPE, INCOMING_SMS_TYPE]
    service_permission_type_to_remove = EMAIL_TYPE
    service_permission_type_remaining = INCOMING_SMS_TYPE

    for spt in service_permission_types_to_create:
        create_service_permission(service_id=sample_service.id, permission=spt)

    dao_remove_service_permission(sample_service.id, service_permission_type_to_remove)

    permissions = dao_fetch_service_permissions(sample_service.id)
    assert len(permissions) == 1
    assert permissions[0].permission == service_permission_type_remaining
    assert permissions[0].service_id == sample_service.id
