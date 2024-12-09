from uuid import UUID

from app import db
from app.dao.dao_utils import autocommit
from app.models import ServicePermission


def dao_fetch_service_permissions(service_id):
    return ServicePermission.query.filter(ServicePermission.service_id == service_id).all()


@autocommit
def dao_add_service_permission(service_id, permission):
    service_permission = ServicePermission(service_id=service_id, permission=permission)
    db.session.add(service_permission)


@autocommit
def dao_remove_service_permissions(service_id: UUID, permissions: list[str]):
    return ServicePermission.query.filter(
        ServicePermission.service_id == service_id, ServicePermission.permission.in_(permissions)
    ).delete()
