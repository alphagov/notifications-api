from app import db
from werkzeug.datastructures import MultiDict
from app.dao import DAOClass
from app.models import (
    Permission,
    Service,
    User,
    MANAGE_SERVICE,
    SEND_MESSAGES,
    MANAGE_API_KEYS,
    MANAGE_TEMPLATES,
    MANAGE_TEAM,
    VIEW_ACTIVITY)


# Default permissions for a service
default_service_permissions = [
    MANAGE_SERVICE,
    SEND_MESSAGES,
    MANAGE_API_KEYS,
    MANAGE_TEMPLATES,
    MANAGE_TEAM,
    VIEW_ACTIVITY]


class PermissionDAO(DAOClass):

    class Meta:
        model = Permission

    def get_query(self, filter_by_dict={}):
        if isinstance(filter_by_dict, dict):
            filter_by_dict = MultiDict(filter_by_dict)
        query = self.Meta.model.query
        if 'id' in filter_by_dict:
            query = query.filter(Permission.id.in_(filter_by_dict.getlist('id')))
        if 'service' in filter_by_dict:
            service_ids = filter_by_dict.getlist('service')
            if len(service_ids) == 1:
                query.filter_by(service=Service.query.get(service_ids[0]))
            # TODO the join method for multiple services
        if 'user' in filter_by_dict:
            user_ids = filter_by_dict.getlist('user')
            if len(user_ids) == 1:
                query = query.filter_by(user=User.query.get(user_ids[0]))
            # TODO the join method for multiple users
        if 'permission' in filter_by_dict:
            query = query.filter(Permission.permission.in_(filter_by_dict.getlist('permission')))
        return query

    def add_default_service_permissions_for_user(self, user, service):
        for name in default_service_permissions:
            permission = Permission(permission=name, user=user, service=service)
            self.create_instance(permission, _commit=False)

    def set_user_permission(self, user, permissions):
        try:
            query = self.get_query(filter_by_dict={'user': user.id})
            query.delete()
            for p in permissions:
                self.create_instance(p, _commit=False)
        except Exception as e:
            db.session.rollback()
            raise e
        else:
            db.session.commit()


permission_dao = PermissionDAO()
