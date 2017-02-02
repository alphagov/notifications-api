from app.dao.permissions_dao import permission_dao
from tests.app.conftest import sample_service as create_service


def test_get_permissions_by_user_id_returns_all_permissions(sample_service):
    permissions = permission_dao.get_permissions_by_user_id(user_id=sample_service.users[0].id)
    assert len(permissions) == 8
    assert sorted(["manage_users",
                   "manage_templates",
                   "manage_settings",
                   "send_texts",
                   "send_emails",
                   "send_letters",
                   "manage_api_keys",
                   "view_activity"]) == sorted([i.permission for i in permissions])


def test_get_permissions_by_user_id_returns_only_active_service(notify_db, notify_db_session, sample_user):
    active_service = create_service(notify_db, notify_db_session, service_name="Active service", user=sample_user)
    inactive_service = create_service(notify_db, notify_db_session, service_name="Inactive service",
                                      user=sample_user)
    inactive_service.active = False
    permissions = permission_dao.get_permissions_by_user_id(user_id=sample_user.id)
    assert len(permissions) == 8
    assert active_service in [i.service for i in permissions]
    assert inactive_service not in [i.service for i in permissions]
