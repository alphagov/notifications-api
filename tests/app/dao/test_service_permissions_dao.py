import pytest

from app.dao.service_permissions_dao import dao_fetch_service_permissions, dao_remove_service_permission
from app.models import EMAIL_TYPE, SMS_TYPE, LETTER_TYPE, INTERNATIONAL_SMS_TYPE, INCOMING_SMS_TYPE

from tests.app.db import create_service_permission, create_service


@pytest.fixture(scope='function')
def service_without_permissions(notify_db, notify_db_session):
    return create_service(service_permissions=[])


def test_create_service_permission(service_without_permissions):
    service_permissions = create_service_permission(
        service_id=service_without_permissions.id, permission=SMS_TYPE)

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


def test_remove_service_permission(service_without_permissions):
    create_service_permission(service_id=service_without_permissions.id, permission=EMAIL_TYPE)
    create_service_permission(service_id=service_without_permissions.id, permission=INCOMING_SMS_TYPE)

    dao_remove_service_permission(service_without_permissions.id, EMAIL_TYPE)

    permissions = dao_fetch_service_permissions(service_without_permissions.id)
    assert len(permissions) == 1
    assert permissions[0].permission == INCOMING_SMS_TYPE
    assert permissions[0].service_id == service_without_permissions.id
