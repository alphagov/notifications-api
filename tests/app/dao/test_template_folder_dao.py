from app import db
from app.dao.service_user_dao import dao_get_service_user
from app.dao.template_folder_dao import (
    dao_delete_template_folder,
    dao_update_template_folder,
)
from app.models import user_folder_permissions
from tests.app.db import create_template_folder


def test_dao_delete_template_folder_deletes_user_folder_permissions(sample_user, sample_service):
    folder = create_template_folder(sample_service)
    service_user = dao_get_service_user(sample_user.id, sample_service.id)
    folder.users = [service_user]
    dao_update_template_folder(folder)

    dao_delete_template_folder(folder)

    assert db.session.query(user_folder_permissions).all() == []
