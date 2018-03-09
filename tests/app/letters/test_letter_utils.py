import pytest

from app.letters.utils import get_bucket_prefix_for_notification


def test_get_bucket_prefix_for_notification_valid_notification(sample_notification):

    bucket_prefix = get_bucket_prefix_for_notification(sample_notification)

    assert bucket_prefix == '{folder}/NOTIFY.{reference}'.format(
        folder=sample_notification.created_at.date(),
        reference=sample_notification.reference
    ).upper()


def test_get_bucket_prefix_for_notification_invalid_notification():
    with pytest.raises(AttributeError):
        get_bucket_prefix_for_notification(None)
