import pytest
from uuid import UUID

from app.constants import NOTIFICATION_DELIVERED, NOTIFICATION_SENT
from app.models import Notification
from tests import create_admin_authorization_header


@pytest.fixture
def replication_client(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            yield client


def test_trigger_process_replication_slot_changes_queues_task(replication_client, mocker):
    mock_task = mocker.patch("app.replication.rest.check_replication_slot_changes")
    auth_header = create_admin_authorization_header()

    response = replication_client.post(
        "/replication/process-slot-changes",
        headers=[auth_header],
    )

    assert response.status_code == 201
    assert response.get_json() == {"message": "check-replication-slot-changes task executed"}
    mock_task.assert_called_once_with()


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
    parsed_changes = [
        {
            "type": "insert",
            "table": "notifications",
            "nextlsn": "0/2",
            "current_row_data": {"id": "1"},
            "previous_row_data": {},
        }
    ]
    mock_get_changes = mocker.patch(
        "app.replication.rest.get_replication_changes",
        return_value=parsed_changes,
    )
    auth_header = create_admin_authorization_header()

    response = replication_client.get(
        "/replication/check-slot-changes",
        headers=[auth_header],
    )

    assert response.status_code == 200
    assert response.get_json() == {"changes": parsed_changes}
    mock_get_changes.assert_called_once_with(peek=True)


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


def test_simulate_notification_load_inserts_and_updates_notifications(replication_client, sample_template):
    auth_header = create_admin_authorization_header()

    response = replication_client.post(
        "/replication/simulate-notification-load",
        headers=[auth_header],
        json={
            "notification_count": 30,
            "updates_per_notification": 2,
            "template_id": str(sample_template.id),
            "random_seed": 7,
        },
    )

    response_json = response.get_json()
    inserted_ids = response_json["inserted_notification_ids"]
    inserted_uuid_ids = [UUID(notification_id) for notification_id in inserted_ids]
    inserted_notifications = Notification.query.filter(Notification.id.in_(inserted_uuid_ids)).all()
    distinct_statuses = {notification.status for notification in inserted_notifications}
    status_breakdown = response_json["status_breakdown"]
    simulated_statuses = {NOTIFICATION_SENT, NOTIFICATION_DELIVERED}

    assert response.status_code == 200
    assert response_json["message"] == "notification send/update load inserted into notifications table"
    assert response_json["notification_count"] == 30
    assert response_json["updates_per_notification"] == 2
    assert response_json["inserted_count"] == 30
    assert response_json["updated_count"] == 60
    assert response_json["service_id"] == str(sample_template.service_id)
    assert response_json["template_id"] == str(sample_template.id)
    assert response_json["template_version"] == sample_template.version
    assert len(inserted_ids) == 20
    assert len(inserted_notifications) == 20
    assert len(status_breakdown) >= 2
    assert len(distinct_statuses) >= 1
    assert sum(status_breakdown.values()) == response_json["inserted_count"]
    assert set(status_breakdown).issubset(simulated_statuses)
    assert distinct_statuses.issubset(simulated_statuses)


@pytest.mark.parametrize(
    "payload, expected_message",
    [
        ({"notification_count": 0}, "notification_count must be greater than 0"),
        ({"notification_count": "abc"}, "notification_count must be an integer"),
        ({"notification_count": 50001}, "notification_count must be less than or equal to 50000"),
        ({"updates_per_notification": 0}, "updates_per_notification must be greater than 0"),
        ({"updates_per_notification": "abc"}, "updates_per_notification must be an integer"),
        (
            {"updates_per_notification": 6},
            "updates_per_notification must be less than or equal to 5",
        ),
        ({"template_id": "not-a-uuid"}, "template_id must be a valid UUID"),
        ({"service_id": "not-a-uuid"}, "service_id must be a valid UUID"),
    ],
)
def test_simulate_notification_load_validates_payload(replication_client, payload, expected_message):
    auth_header = create_admin_authorization_header()

    response = replication_client.post(
        "/replication/simulate-notification-load",
        headers=[auth_header],
        json=payload,
    )

    assert response.status_code == 400
    assert response.get_json() == {"message": expected_message}
