from app.dao import DAOClass
from app.models import Permission


# Service Permissions
manage_service = 'manage_service'
send_messages = 'send_messages'
manage_api_keys = 'manage_api_keys'
# Default permissions for a service
default_service_permissions = [manage_service, send_messages, manage_api_keys]


class PermissionDAO(DAOClass):

    class Meta:
        model = Permission

    def add_default_service_permissions_for_user(self, user, service):
        for name in default_service_permissions:
            permission = Permission(permission=name, user=user, service=service)
            self.create_instance(permission, _commit=False)


permission_dao = PermissionDAO()
