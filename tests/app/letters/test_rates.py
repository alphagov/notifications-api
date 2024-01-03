from datetime import datetime, timedelta

from freezegun import freeze_time

from tests.app.db import create_letter_rate


@freeze_time("2024-01-02T12:00:00")
def test_letter_rates(admin_request, notify_db_session):
    now = datetime.utcnow()
    tomorrow = datetime.utcnow() + timedelta(days=1)
    yesterday = datetime.utcnow() - timedelta(days=1)

    # Should be returned
    create_letter_rate(start_date=now, rate=0.66, post_class="first", sheet_count=1)
    create_letter_rate(start_date=now, rate=0.33, post_class="second", sheet_count=2)
    create_letter_rate(start_date=yesterday, end_date=tomorrow, rate=0.84, post_class="europe", sheet_count=3)
    create_letter_rate(start_date=yesterday, end_date=tomorrow, rate=0.84, post_class="rest-of-world", sheet_count=4)

    # Expired (should not be returned)
    create_letter_rate(start_date=yesterday, end_date=now)

    # Future (should not be returned)
    create_letter_rate(start_date=tomorrow)
    create_letter_rate(start_date=tomorrow, end_date=tomorrow + timedelta(days=1))

    # Non crown (should not be returned)
    create_letter_rate(start_date=now, crown=False)

    json_response = admin_request.get("letter_rates.get_letter_rates")

    assert json_response == [
        {"post_class": "first", "rate": "0.66", "sheet_count": 1, "start_date": "2024-01-02T12:00:00"},
        {"post_class": "second", "rate": "0.33", "sheet_count": 2, "start_date": "2024-01-02T12:00:00"},
        {"post_class": "europe", "rate": "0.84", "sheet_count": 3, "start_date": "2024-01-01T12:00:00"},
        {"post_class": "rest-of-world", "rate": "0.84", "sheet_count": 4, "start_date": "2024-01-01T12:00:00"},
    ]
