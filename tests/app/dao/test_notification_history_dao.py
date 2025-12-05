import pytest

from app.models import NotificationHistory
from tests.app.db import create_notification_history


@pytest.mark.parametrize("postage", ["first", "second", "europe", "rest-of-world", "economy"])
def test_create_notification_history_with_various_postage_values(notify_db_session, sample_letter_template, postage):
    created = create_notification_history(
        sample_letter_template,
        status="delivered",
        created_at="2024-01-01T10:00:00",
        sent_at="2024-01-01T10:01:00",
        updated_at="2024-01-01T10:02:00",
        postage=postage,
    )

    retrieved = NotificationHistory.query.get(created.id)
    assert retrieved is not None
    assert retrieved.postage == postage
    assert retrieved.notification_type == "letter"
    assert retrieved.status == "delivered"
