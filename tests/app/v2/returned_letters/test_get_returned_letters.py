import uuid
from datetime import UTC, datetime, timedelta

from freezegun import freeze_time
from notifications_utils.testing.comparisons import AnyStringMatching, RestrictedAny

from app.constants import NOTIFICATION_RETURNED_LETTER
from app.utils import DATETIME_FORMAT_NO_TIMEZONE
from tests.app.db import (
    create_api_key,
    create_job,
    create_notification,
    create_notification_history,
    create_returned_letter,
    create_service,
    create_template,
)


@freeze_time("2026-06-22 13:30")
def test_v2_get_returned_letter_summary(api_client_request, sample_service):
    create_returned_letter(sample_service, reported_at=datetime.now(UTC) - timedelta(days=3))
    create_returned_letter(sample_service, reported_at=datetime.now(UTC))
    create_returned_letter(sample_service, reported_at=datetime.now(UTC))

    response = api_client_request.get(
        sample_service.id,
        "v2_returned_letters.get_returned_letter_summary",
        _expected_status=200,
    )

    assert len(response) == 2

    assert response == [
        {"returned_letter_count": 2, "report_date": "2026-06-22"},
        {"returned_letter_count": 1, "report_date": "2026-06-19"},
    ]


def test_v2_get_returned_letter_summary_error_for_non_live_keys(api_client_request, sample_service):
    api_client_request.get(
        sample_service.id,
        "v2_returned_letters.get_returned_letter_summary",
        _api_key_type='test',
        _expected_status=403,
    )
