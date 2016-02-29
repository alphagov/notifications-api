from app.dao import DAOClass
from app.models import Permission


class PermissionDAO(DAOClass):

    class Meta:
        model = Permission


permission_dao = PermissionDAO()
