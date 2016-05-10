import uuid

from app import db
from app.models import Service
from sqlalchemy import asc

from app.dao.dao_utils import (
    transactional,
    version_class
)

from app.models import (
    NotificationStatistics,
    TemplateStatistics,
    ProviderStatistics,
    VerifyCode,
    ApiKey,
    Template,
    Job,
    Notification,
    Permission,
    User,
    InvitedUser,
    Service
)


def dao_fetch_all_services():
    return Service.query.order_by(asc(Service.created_at)).all()


def dao_fetch_service_by_id(service_id):
    return Service.query.filter_by(id=service_id).one()


def dao_fetch_all_services_by_user(user_id):
    return Service.query.filter(Service.users.any(id=user_id)).order_by(asc(Service.created_at)).all()


def dao_fetch_service_by_id_and_user(service_id, user_id):
    return Service.query.filter(Service.users.any(id=user_id)).filter_by(id=service_id).one()


@transactional
@version_class(Service)
def dao_create_service(service, user):
    from app.dao.permissions_dao import permission_dao
    service.users.append(user)
    permission_dao.add_default_service_permissions_for_user(user, service)
    service.id = uuid.uuid4()  # must be set now so version history model can use same id
    db.session.add(service)


@transactional
@version_class(Service)
def dao_update_service(service):
    db.session.add(service)


def dao_add_user_to_service(service, user, permissions=[]):
    try:
        from app.dao.permissions_dao import permission_dao
        service.users.append(user)
        permission_dao.set_user_service_permission(user, service, permissions, _commit=False)
        db.session.add(service)
    except Exception as e:
        db.session.rollback()
        raise e
    else:
        db.session.commit()


def dao_remove_user_from_service(service, user):
    try:
        from app.dao.permissions_dao import permission_dao
        permission_dao.remove_user_service_permissions(user, service)
        service.users.remove(user)
        db.session.add(service)
    except Exception as e:
        db.session.rollback()
        raise e
    else:
        db.session.commit()


def delete_service_and_all_associated_db_objects(service):

    def _delete_commit(query):
        query.delete()
        db.session.commit()

    _delete_commit(NotificationStatistics.query.filter_by(service=service))
    _delete_commit(TemplateStatistics.query.filter_by(service=service))
    _delete_commit(ProviderStatistics.query.filter_by(service=service))
    _delete_commit(InvitedUser.query.filter_by(service=service))
    _delete_commit(Permission.query.filter_by(service=service))
    _delete_commit(ApiKey.query.filter_by(service=service))
    _delete_commit(Notification.query.filter_by(service=service))
    _delete_commit(Job.query.filter_by(service=service))
    _delete_commit(Template.query.filter_by(service=service))

    verify_codes = VerifyCode.query.join(User).filter(User.id.in_([x.id for x in service.users]))
    list(map(db.session.delete, verify_codes))
    db.session.commit()
    users = [x for x in service.users]
    map(service.users.remove, users)
    [service.users.remove(x) for x in users]
    db.session.delete(service)
    db.session.commit()
    list(map(db.session.delete, users))
    db.session.commit()
