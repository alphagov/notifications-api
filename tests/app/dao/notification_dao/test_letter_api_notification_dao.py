from app.models import (
    Notification,
    NOTIFICATION_CREATED,
    NOTIFICATION_PENDING,
    NOTIFICATION_SENDING,
    KEY_TYPE_TEST,
    KEY_TYPE_NORMAL,
    LETTER_TYPE
)
from app.dao.notifications_dao import dao_set_created_live_letter_api_notifications_to_pending

from tests.app.db import create_notification, create_service, create_template


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


def test_should_ignore_letters_as_pdf(
    sample_letter_notification,
):
    service = create_service(service_permissions=[LETTER_TYPE, 'letters_as_pdf'])
    template = create_template(service, template_type=LETTER_TYPE)
    create_notification(template)

    all_noti = Notification.query.all()
    assert len(all_noti) == 2

    ret = dao_set_created_live_letter_api_notifications_to_pending()

    assert sample_letter_notification.status == NOTIFICATION_PENDING
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
