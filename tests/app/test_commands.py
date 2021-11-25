import uuid

from app.commands import local_dev_broadcast_permissions, replay_callbacks
from app.config import QueueNames
from app.dao.services_dao import dao_add_user_to_service
from tests.app.db import create_service_callback_api, create_user


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
    mock_apply = mocker.patch('app.commands.send_delivery_status_to_service.apply_async')
    mock_update = mocker.patch('app.commands.create_delivery_status_callback_data')
    mock_update.return_value = 'encrypted_status_update'

    file_path = tmpdir + 'callback_ids.txt'
    missing_notification_id = uuid.uuid4()

    with open(file_path, 'w') as f:
        f.write(str(sample_notification.id) + "\n")
        f.write(str(missing_notification_id) + "\n")

    result = notify_api.test_cli_runner().invoke(
        replay_callbacks, ['-f', file_path]
    )

    mock_apply.assert_not_called()
    assert f'{missing_notification_id} was not found' in result.output
    assert "Callback api was not found" in result.output

    # Now re-run with the callback API in place
    create_service_callback_api(service=sample_service, bearer_token='foo')

    result = notify_api.test_cli_runner().invoke(
        replay_callbacks, ['-f', file_path]
    )

    mock_apply.assert_called_once_with(
        [str(sample_notification.id), 'encrypted_status_update'],
        queue=QueueNames.CALLBACKS
    )

    assert result.exit_code == 0
