from pytest_mock import MockerFixture

from app.metrics.notification import (
    _notifications_created,
    increment_notifications_created,
)


def test_increment_notifications_created(mocker: MockerFixture) -> None:
    notifications_mock = mocker.patch.object(_notifications_created, "add")

    increment_notifications_created(key_type="team", notification_type="email", service_id="service-a1b2c3")

    notifications_mock.assert_called_once_with(
        1, {"key.type": "team", "notification.type": "email", "service.id": "service-a1b2c3"}
    )
