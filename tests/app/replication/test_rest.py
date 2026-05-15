import pytest

from tests import create_admin_authorization_header


@pytest.fixture
def replication_client(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            yield client


def test_trigger_process_replication_slot_changes_queues_task(replication_client, mocker):
    mock_apply_async = mocker.patch(
        "app.replication.rest.check_replication_slot_changes.apply_async"
    )
    auth_header = create_admin_authorization_header()

    response = replication_client.post(
        "/replication/process-slot-changes",
        headers=[auth_header],
    )

    assert response.status_code == 201
    assert response.get_json() == {"message": "check-replication-slot-changes task queued"}
    mock_apply_async.assert_called_once_with()


def test_trigger_process_replication_slot_changes_requires_auth(replication_client):
    response = replication_client.post("/replication/process-slot-changes")

    assert response.status_code == 401


def test_trigger_process_replication_slot_changes_rejects_get(replication_client):
    auth_header = create_admin_authorization_header()

    response = replication_client.get(
        "/replication/process-slot-changes",
        headers=[auth_header],
    )

    assert response.status_code == 405
