import pytest

from app.dao.service_permissions_dao import dao_fetch_service_permissions, dao_remove_service_permission
from app.models import EMAIL_TYPE, SMS_TYPE, LETTER_TYPE, INTERNATIONAL_SMS_TYPE, INCOMING_SMS_TYPE

from tests.app.db import create_service_permission


def test_create_service_permission(sample_service):
    service_permissions = create_service_permission(service_id=sample_service.id, permission=SMS_TYPE)

    assert len(service_permissions) == 1
    assert service_permissions[0].service_id == sample_service.id
    assert service_permissions[0].permission == SMS_TYPE


def test_fetch_service_permissions_gets_service_permissions(sample_service):
    create_service_permission(service_id=sample_service.id, permission=LETTER_TYPE)
    create_service_permission(service_id=sample_service.id, permission=INTERNATIONAL_SMS_TYPE)
    create_service_permission(service_id=sample_service.id, permission=SMS_TYPE)

    service_permissions = dao_fetch_service_permissions(sample_service.id)

    assert len(service_permissions) == 3
    assert all(sp.service_id == sample_service.id for sp in service_permissions)
    assert all(sp.permission in [LETTER_TYPE, INTERNATIONAL_SMS_TYPE, SMS_TYPE] for sp in service_permissions)


def test_remove_service_permission(sample_service):
    create_service_permission(service_id=sample_service.id, permission=EMAIL_TYPE)
    create_service_permission(service_id=sample_service.id, permission=INCOMING_SMS_TYPE)

    dao_remove_service_permission(sample_service.id, EMAIL_TYPE)

    permissions = dao_fetch_service_permissions(sample_service.id)
    assert len(permissions) == 1
    assert permissions[0].permission == INCOMING_SMS_TYPE
    assert permissions[0].service_id == sample_service.id
