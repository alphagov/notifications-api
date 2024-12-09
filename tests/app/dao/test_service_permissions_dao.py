import pytest

from app.constants import (
    EMAIL_TYPE,
    INBOUND_SMS_TYPE,
    INTERNATIONAL_SMS_TYPE,
    LETTER_TYPE,
    SMS_TYPE,
)
from app.dao.service_permissions_dao import (
    dao_fetch_service_permissions,
    dao_remove_service_permission,
)
from tests.app.db import create_service, create_service_permission


@pytest.fixture(scope="function")
def service_without_permissions(notify_db_session):
    return create_service(service_permissions=[])


def test_create_service_permission(service_without_permissions):
    service_permissions = create_service_permission(service_id=service_without_permissions.id, permission=SMS_TYPE)

    assert len(service_permissions) == 1
    assert service_permissions[0].service_id == service_without_permissions.id
    assert service_permissions[0].permission == SMS_TYPE


def test_fetch_service_permissions_gets_service_permissions(service_without_permissions):
    create_service_permission(service_id=service_without_permissions.id, permission=LETTER_TYPE)
    create_service_permission(service_id=service_without_permissions.id, permission=INTERNATIONAL_SMS_TYPE)
    create_service_permission(service_id=service_without_permissions.id, permission=SMS_TYPE)

    service_permissions = dao_fetch_service_permissions(service_without_permissions.id)

    assert len(service_permissions) == 3
    assert all(sp.service_id == service_without_permissions.id for sp in service_permissions)
    assert all(sp.permission in [LETTER_TYPE, INTERNATIONAL_SMS_TYPE, SMS_TYPE] for sp in service_permissions)


def test_remove_service_permission():
    service = create_service(service_permissions=[INBOUND_SMS_TYPE, EMAIL_TYPE])
    dao_remove_service_permission(service.id, [INBOUND_SMS_TYPE])
    permissions = dao_fetch_service_permissions(service.id)

    assert len(permissions) == 1
    assert permissions[0].permission == EMAIL_TYPE
