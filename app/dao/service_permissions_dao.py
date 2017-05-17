from app import db
from app.dao.dao_utils import transactional
from app.models import ServicePermission, SERVICE_PERMISSION_TYPES


def dao_fetch_service_permissions(service_id):
    return ServicePermission.query.filter(
        ServicePermission.service_id == service_id).all()


@transactional
def dao_add_service_permission(service_id, permission):
    service_permission = ServicePermission(service_id=service_id, permission=permission)
    db.session.add(service_permission)


def dao_remove_service_permission(service_id, permission):
    deleted = ServicePermission.query.filter(
        ServicePermission.service_id == service_id,
        ServicePermission.permission == permission).delete()
    db.session.commit()
    return deleted
