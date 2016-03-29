from app.models import (
    MANAGE_USERS,
    MANAGE_TEMPLATES,
    MANAGE_SETTINGS,
    SEND_TEXTS,
    SEND_EMAILS,
    SEND_LETTERS,
    MANAGE_API_KEYS,
    ACCESS_DEVELOPER_DOCS,
    VIEW_ACTIVITY
)

from app.schemas import permission_schema


permissions_groups = {'send_messages': [SEND_TEXTS, SEND_EMAILS, SEND_LETTERS],
                      'manage_service': [MANAGE_USERS, MANAGE_SETTINGS, MANAGE_TEMPLATES],
                      'manage_api_keys': [MANAGE_API_KEYS, ACCESS_DEVELOPER_DOCS],
                      VIEW_ACTIVITY: [VIEW_ACTIVITY]}


def get_permissions_by_group(permission_groups):
    requested_permissions = []
    for group in permission_groups:
        permissions = permissions_groups[group]
        for permission in permissions:
            requested_permissions.append({'permission': permission})
    permissions, errors = permission_schema.load(requested_permissions, many=True)
    return permissions
