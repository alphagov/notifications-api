from datetime import UTC, datetime, timedelta

from freezegun import freeze_time

from tests.app.db import create_rate


@freeze_time("2024-01-02T12:00:00")
def test_sms_rate(admin_request, notify_db_session):
    now = datetime.now(UTC).replace(tzinfo=None)
    tomorrow = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1)
    yesterday = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)

    # Older (should not be returned)
    create_rate(start_date=yesterday, value=1.23, notification_type="sms")

    # Should be returned
    create_rate(start_date=now, value=4.56, notification_type="sms")

    # Future (should not be returned)
    create_rate(start_date=tomorrow, value=7.89, notification_type="sms")

    json_response = admin_request.get("sms_rate.get_sms_rate")

    assert json_response == {
        "rate": 4.56,
        "valid_from": "2024-01-02T12:00:00",
    }
