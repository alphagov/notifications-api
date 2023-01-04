import json
import uuid

from freezegun import freeze_time

from tests import create_admin_authorization_header
from tests.app.db import create_notification, create_service, create_template


class TestGetNotificationEvents:
    def test_404(self, client, notify_db_session):
        response = client.get(
            path="/notifications/{}/events".format("foo"),
            headers=[create_admin_authorization_header()],
        )
        assert response.status_code == 404

    @freeze_time("2023-01-01T12:00:00Z")
    def test_get_success(self, mocker, client, notify_db_session):
        service_1 = create_service(service_name="1", email_from="1")

        service_1_template = create_template(service_1)

        service_1_notifications = [
            create_notification(service_1_template),
            create_notification(service_1_template),
            create_notification(service_1_template),
        ]

        for notification in service_1_notifications:
            response = client.get(
                path="/notifications/{}/events".format(notification.id),
                headers=[create_admin_authorization_header()],
            )
            resp = json.loads(response.get_data(as_text=True))
            assert resp["events"] == [
                {
                    "id": mocker.ANY,
                    "notification_id": str(notification.id),
                    "happened_at": "2023-01-01T12:00:00.000000Z",
                    "status": "created",
                    "notes": None,
                }
            ]
            assert response.status_code == 200

    def test_requires_admin_auth(self, client):
        response = client.get(
            path="/notifications/{}/events".format(uuid.uuid4()),
        )
        assert response.status_code == 401
