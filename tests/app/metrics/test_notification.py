from pytest_mock import MockerFixture

from app.metrics.notification import (
    _notifications,
    _notifications_by_service_id,
    increment_notifications_created,
)


def test_increment_notifications_created(mocker: MockerFixture) -> None:
    notifications_mock = mocker.patch.object(_notifications, "add")
    notifications_by_service_id_mock = mocker.patch.object(_notifications_by_service_id, "add")

    increment_notifications_created(key_type="team", notification_type="email", service_id="service-a1b2c3")

    notifications_mock.assert_called_once_with(1, {"key.type": "team", "notification.type": "email"})

    notifications_by_service_id_mock.assert_called_once_with(1, {"service.id": "service-a1b2c3"})
