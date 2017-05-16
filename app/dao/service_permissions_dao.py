from sqlalchemy import exc

from app import db
from app.dao.dao_utils import transactional
from app.models import Service, ServicePermission, SERVICE_PERMISSION_TYPES


def dao_fetch_service_permissions(service_id):
    return ServicePermission.query.filter(
        ServicePermission.service_id == service_id).all()


@transactional
def dao_add_and_commit_service_permission(service_id, permission):
    if permission not in SERVICE_PERMISSION_TYPES:
        raise ValueError("'{}' not of service permission type: {}".format(permission, SERVICE_PERMISSION_TYPES))

    service_permission = ServicePermission(service_id=service_id, permission=permission)

    db.session.add(service_permission)


def dao_remove_service_permission(service_id, permission=None):
    return ServicePermission.query.filter(
        ServicePermission.service_id == service_id,
        ServicePermission.permission == permission if permission else None).delete()
