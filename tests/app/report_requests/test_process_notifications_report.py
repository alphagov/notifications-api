import pytest
from freezegun import freeze_time

from app.constants import (
    KEY_TYPE_NORMAL,
    NOTIFICATION_CREATED,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_REQUEST_REPORT_ALL,
    NOTIFICATION_REQUEST_REPORT_DELIVERED,
    NOTIFICATION_REQUEST_REPORT_SENDING,
    NOTIFICATION_SENDING,
    NOTIFICATION_SENT,
    REPORT_REQUEST_NOTIFICATIONS,
)
from app.dao.notifications_dao import (
    get_notifications_for_service,
)
from app.report_requests.process_notifications_report import (
    convert_notifications_to_csv,
    get_notifications_by_batch,
)
from tests.app.db import (
    create_api_key,
    create_notification,
    create_service,
    create_service_data_retention,
)


def test_convert_notifications_to_csv_when_empty_notifications(sample_sms_template):
    csv_data = convert_notifications_to_csv([])

    expected_csv = []

    assert expected_csv == csv_data


@freeze_time("2025-03-19 18:25:33")
def test_convert_notifications_to_csv_values(sample_sms_template):
    service = create_service(check_if_service_exists=True)
    api_key = create_api_key(service=service, key_type=KEY_TYPE_NORMAL, id="8e33368c-3965-4ae1-ab55-4f9d3275f84d")

    create_notification(template=sample_sms_template, status="delivered", api_key=api_key)
    create_notification(template=sample_sms_template, status="sending", api_key=api_key)
    create_notification(template=sample_sms_template, status="sending", api_key=api_key)
    create_notification(template=sample_sms_template, status="created", api_key=api_key)
    create_notification(template=sample_sms_template, status="delivered", api_key=api_key)

    notifications = get_notifications_for_service(service.id)
    serialized_notifications = [notification.serialize_for_csv() for notification in notifications]
    csv_data = convert_notifications_to_csv(serialized_notifications)

    expected_csv = [
        (
            "+447700900855",
            "",
            "Template Name",
            "sms",
            "",
            "",
            "",
            "Delivered",
            "2025-03-19 18:25:33",
            "normal api key 8e33368c-3965-4ae1-ab55-4f9d3275f84d",
        ),
        (
            "+447700900855",
            "",
            "Template Name",
            "sms",
            "",
            "",
            "",
            "Sending",
            "2025-03-19 18:25:33",
            "normal api key 8e33368c-3965-4ae1-ab55-4f9d3275f84d",
        ),
        (
            "+447700900855",
            "",
            "Template Name",
            "sms",
            "",
            "",
            "",
            "Sending",
            "2025-03-19 18:25:33",
            "normal api key 8e33368c-3965-4ae1-ab55-4f9d3275f84d",
        ),
        (
            "+447700900855",
            "",
            "Template Name",
            "sms",
            "",
            "",
            "",
            "Sending",
            "2025-03-19 18:25:33",
            "normal api key 8e33368c-3965-4ae1-ab55-4f9d3275f84d",
        ),
        (
            "+447700900855",
            "",
            "Template Name",
            "sms",
            "",
            "",
            "",
            "Delivered",
            "2025-03-19 18:25:33",
            "normal api key 8e33368c-3965-4ae1-ab55-4f9d3275f84d",
        ),
    ]

    assert expected_csv == csv_data


@pytest.mark.parametrize(
    "page_size, page, expected_notifications, notification_report_request_status",
    [
        (5, 1, 5, NOTIFICATION_REQUEST_REPORT_ALL),
        (2, 2, 2, NOTIFICATION_REQUEST_REPORT_SENDING),
        (1, 1, 1, NOTIFICATION_REQUEST_REPORT_SENDING),
        (2, 1, 2, NOTIFICATION_REQUEST_REPORT_DELIVERED),
    ],
)
def test_get_notifications_by_batch(
    page_size,
    page,
    notification_report_request_status,
    expected_notifications,
    sample_email_template,
    sample_sms_template,
):
    service = create_service(check_if_service_exists=True)
    create_service_data_retention(service=service)
    api_key = create_api_key(service=service, key_type=KEY_TYPE_NORMAL, id="8e33368c-3965-4ae1-ab55-4f9d3275f84d")

    create_notification(template=sample_email_template, status=NOTIFICATION_SENDING, api_key=api_key)
    create_notification(template=sample_sms_template, status=NOTIFICATION_SENDING, api_key=api_key)
    create_notification(template=sample_email_template, status=NOTIFICATION_DELIVERED, api_key=api_key)
    create_notification(template=sample_email_template, status=NOTIFICATION_DELIVERED, api_key=api_key)
    create_notification(template=sample_email_template, status=NOTIFICATION_SENDING, api_key=api_key)
    create_notification(template=sample_email_template, status=NOTIFICATION_SENDING, api_key=api_key)
    create_notification(template=sample_email_template, status=NOTIFICATION_CREATED, api_key=api_key)
    create_notification(template=sample_email_template, status=NOTIFICATION_SENT, api_key=api_key)

    notifications = get_notifications_by_batch(
        service_id=service.id,
        notification_status=notification_report_request_status,
        template_type="email",
        page=page,
        page_size=page_size,
        limit_days=2,
    )
    assert len(notifications) == expected_notifications
