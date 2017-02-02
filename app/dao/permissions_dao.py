from app import db
from werkzeug.datastructures import MultiDict
from app.dao import DAOClass
from app.models import (
    Permission,
    Service,
    User,
    MANAGE_USERS,
    MANAGE_TEMPLATES,
    MANAGE_SETTINGS,
    SEND_TEXTS,
    SEND_EMAILS,
    SEND_LETTERS,
    MANAGE_API_KEYS,
    VIEW_ACTIVITY)


# Default permissions for a service
default_service_permissions = [
    MANAGE_USERS,
    MANAGE_TEMPLATES,
    MANAGE_SETTINGS,
    SEND_TEXTS,
    SEND_EMAILS,
    SEND_LETTERS,
    MANAGE_API_KEYS,
    VIEW_ACTIVITY]


class PermissionDAO(DAOClass):

    class Meta:
        model = Permission

    def add_default_service_permissions_for_user(self, user, service):
        for name in default_service_permissions:
            permission = Permission(permission=name, user=user, service=service)
            self.create_instance(permission, _commit=False)

    def remove_user_service_permissions(self, user, service):
        query = self.Meta.model.query.filter_by(user=user, service=service)
        query.delete()

    def set_user_service_permission(self, user, service, permissions, _commit=False, replace=False):
        try:
            if replace:
                query = self.Meta.model.query.filter_by(user=user, service=service)
                query.delete()
            for p in permissions:
                p.user = user
                p.service = service
                self.create_instance(p, _commit=False)
        except Exception as e:
            if _commit:
                db.session.rollback()
            raise e
        else:
            if _commit:
                db.session.commit()

    def get_permissions_by_user_id(self, user_id):
        return self.Meta.model.query.filter_by(user_id=user_id)\
                                    .join(Permission.service).filter_by(active=True).all()


permission_dao = PermissionDAO()
