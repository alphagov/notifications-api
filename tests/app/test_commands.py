import uuid

from app.commands import local_dev_broadcast_permissions
from app.dao.services_dao import dao_add_user_to_service
from tests.app.db import create_user


def test_local_dev_broadcast_permissions(
    sample_service,
    sample_broadcast_service,
    notify_api,
):
    # create_user will pull existing unless email is unique
    user = create_user(email=f'{uuid.uuid4()}@example.com')
    dao_add_user_to_service(sample_service, user)
    dao_add_user_to_service(sample_broadcast_service, user)

    assert len(user.get_permissions(sample_service.id)) == 0
    assert len(user.get_permissions(sample_broadcast_service.id)) == 0

    notify_api.test_cli_runner().invoke(
        local_dev_broadcast_permissions, ['-u', user.id]
    )

    assert len(user.get_permissions(sample_service.id)) == 0
    assert len(user.get_permissions(sample_broadcast_service.id)) > 0
