import uuid

from app.commands import local_dev_broadcast_permissions, replay_callbacks
from app.dao.services_dao import dao_add_user_to_service
from tests.app.db import create_user


def test_local_dev_broadcast_permissions(
    sample_service,
    sample_broadcast_service,
    notify_api,
):
    user = create_user()
    dao_add_user_to_service(sample_service, user)
    dao_add_user_to_service(sample_broadcast_service, user)

    assert len(user.get_permissions(sample_service.id)) == 0
    assert len(user.get_permissions(sample_broadcast_service.id)) == 0

    notify_api.test_cli_runner().invoke(
        local_dev_broadcast_permissions, ['-u', user.id]
    )

    assert len(user.get_permissions(sample_service.id)) == 0
    assert len(user.get_permissions(sample_broadcast_service.id)) > 0


def test_replay_callbacks(
    mocker,
    sample_service,
    sample_notification,
    tmpdir,
    notify_api,
):
    mock_task = mocker.patch('app.commands.check_and_queue_callback_task')
    file_path = tmpdir + 'callback_ids.txt'
    missing_notification_id = uuid.uuid4()

    with open(file_path, 'w') as f:
        f.write(str(sample_notification.id) + "\n")
        f.write(str(missing_notification_id) + "\n")

    result = notify_api.test_cli_runner().invoke(
        replay_callbacks, ['-f', file_path]
    )

    assert f'{missing_notification_id} was not found' in result.output
    mock_task.assert_called_once_with(sample_notification)
    assert result.exit_code == 0
