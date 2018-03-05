import pytest
from flask import current_app

from app.letters.utils import get_bucket_prefix_for_notification, is_precompiled_letter


def test_get_bucket_prefix_for_notification_valid_notification(sample_notification):

    bucket_prefix = get_bucket_prefix_for_notification(sample_notification)

    assert bucket_prefix == '{folder}/NOTIFY.{reference}'.format(
        folder=sample_notification.created_at.date(),
        reference=sample_notification.reference
    ).upper()


def test_get_bucket_prefix_for_notification_invalid_notification():
    with pytest.raises(AttributeError):
        get_bucket_prefix_for_notification(None)


def test_is_precompiled_letter_false(sample_letter_template):
    assert not is_precompiled_letter(sample_letter_template)


def test_is_precompiled_letter_true(sample_letter_template):
    sample_letter_template.hidden = True
    sample_letter_template.name = current_app.config['PRECOMPILED_TEMPLATE_NAME']
    assert is_precompiled_letter(sample_letter_template)
