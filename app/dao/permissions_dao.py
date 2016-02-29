from app.dao import DAOClass
from app.models import (Permission, Service, User)
from werkzeug.datastructures import MultiDict


# Service Permissions
manage_service = 'manage_service'
send_messages = 'send_messages'
manage_api_keys = 'manage_api_keys'
# Default permissions for a service
default_service_permissions = [manage_service, send_messages, manage_api_keys]


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
            user_ids = filter_by_dict.getlist('service')
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


permission_dao = PermissionDAO()
