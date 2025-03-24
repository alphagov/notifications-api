from freezegun import freeze_time

from app.constants import (
    KEY_TYPE_NORMAL,
)
from app.dao.notifications_dao import (
    get_notifications_for_service,
)
from app.report_requests.process_notifications_report import (
    convert_notifications_to_csv,
)
from tests.app.db import (
    create_api_key,
    create_notification,
    create_service,
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
