from pytest_mock import MockerFixture

from app.metrics.notification import (
    _notifications,
    _notifications_by_job_id,
    _notifications_by_service_id,
    increment_notifications_created,
)


def test_increment_notifications_created(mocker: MockerFixture) -> None:
    notifications_mock = mocker.patch.object(_notifications, "add")
    notifications_by_service_id_mock = mocker.patch.object(_notifications_by_service_id, "add")
    notifications_by_job_id_mock = mocker.patch.object(_notifications_by_job_id, "add")

    increment_notifications_created(
        job_id="job-a1b2c3", key_type="team", notification_type="email", service_id="service-a1b2c3"
    )

    notifications_mock.assert_called_once_with(1, {"key.type": "team", "notification.type": "email"})

    notifications_by_service_id_mock.assert_called_once_with(1, {"service.id": "service-a1b2c3"})

    notifications_by_job_id_mock.assert_called_once_with(1, {"job.id": "job-a1b2c3"})


def test_increment_notifications_created_with_no_job_id(mocker: MockerFixture) -> None:
    notifications_mock = mocker.patch.object(_notifications, "add")
    notifications_by_service_id_mock = mocker.patch.object(_notifications_by_service_id, "add")
    notifications_by_job_id_mock = mocker.patch.object(_notifications_by_job_id, "add")

    increment_notifications_created(
        job_id=None, key_type="team", notification_type="email", service_id="service-a1b2c3"
    )

    notifications_mock.assert_called_once_with(1, {"key.type": "team", "notification.type": "email"})

    notifications_by_service_id_mock.assert_called_once_with(1, {"service.id": "service-a1b2c3"})

    notifications_by_job_id_mock.assert_not_called()
