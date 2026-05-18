import pytest

from tests import create_admin_authorization_header


@pytest.fixture
def replication_client(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            yield client


def test_trigger_process_replication_slot_changes_queues_task(replication_client, mocker):
    mock_apply_async = mocker.patch("app.replication.rest.check_replication_slot_changes.apply_async")
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


def test_trigger_check_replication_slot_changes_returns_data(replication_client, mocker):
    mock_result = mocker.Mock()
    raw_changes = [{"lsn": "0/1", "xid": 1, "data": "mock-change"}]
    parsed_changes = [
        {"type": "insert", "table": "notifications", "current_row_data": {"id": "1"}, "previous_row_data": {}}
    ]
    mock_result.mappings.return_value.all.return_value = raw_changes
    mock_execute = mocker.patch(
        "app.replication.rest.db.session.execute",
        return_value=mock_result,
    )
    mock_process_changes = mocker.patch(
        "app.replication.rest.process_replication_changes",
        return_value=parsed_changes,
    )
    auth_header = create_admin_authorization_header()

    response = replication_client.get(
        "/replication/check-slot-changes",
        headers=[auth_header],
    )

    assert response.status_code == 200
    assert response.get_json() == {"changes": parsed_changes}
    mock_execute.assert_called_once()
    mock_result.mappings.assert_called_once_with()
    mock_result.mappings.return_value.all.assert_called_once_with()
    mock_process_changes.assert_called_once_with(raw_changes)


def test_trigger_check_replication_slot_changes_requires_auth(replication_client):
    response = replication_client.get("/replication/check-slot-changes")

    assert response.status_code == 401


def test_trigger_check_replication_slot_changes_rejects_post(replication_client):
    auth_header = create_admin_authorization_header()

    response = replication_client.post(
        "/replication/check-slot-changes",
        headers=[auth_header],
    )

    assert response.status_code == 405
