from app.models import (
    NOTIFICATION_CREATED,
    NOTIFICATION_PENDING,
    NOTIFICATION_SENDING,
    KEY_TYPE_TEST,
    KEY_TYPE_NORMAL
)
from app.dao.notifications_dao import dao_set_created_live_letter_api_notifications_to_pending

from tests.app.db import create_notification


def test_should_only_get_letter_notifications(
    sample_letter_notification,
    sample_email_notification,
    sample_notification
):
    ret = dao_set_created_live_letter_api_notifications_to_pending()

    assert sample_letter_notification.status == NOTIFICATION_PENDING
    assert sample_email_notification.status == NOTIFICATION_CREATED
    assert sample_notification.status == NOTIFICATION_CREATED
    assert ret == [sample_letter_notification]


def test_should_only_get_created_letters(sample_letter_template):
    created_noti = create_notification(sample_letter_template, status=NOTIFICATION_CREATED)
    create_notification(sample_letter_template, status=NOTIFICATION_PENDING)
    create_notification(sample_letter_template, status=NOTIFICATION_SENDING)

    ret = dao_set_created_live_letter_api_notifications_to_pending()

    assert ret == [created_noti]


def test_should_only_get_api_letters(sample_letter_template, sample_letter_job):
    api_noti = create_notification(sample_letter_template)
    create_notification(sample_letter_template, job=sample_letter_job)

    ret = dao_set_created_live_letter_api_notifications_to_pending()

    assert ret == [api_noti]


def test_should_only_get_normal_api_letters(sample_letter_template):
    live_noti = create_notification(sample_letter_template, key_type=KEY_TYPE_NORMAL)
    create_notification(sample_letter_template, key_type=KEY_TYPE_TEST)

    ret = dao_set_created_live_letter_api_notifications_to_pending()

    assert ret == [live_noti]
