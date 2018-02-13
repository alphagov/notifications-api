from app.models import (
    Notification,
    NOTIFICATION_CREATED,
    NOTIFICATION_PENDING,
    NOTIFICATION_SENDING,
    KEY_TYPE_TEST,
    KEY_TYPE_NORMAL,
    LETTER_TYPE,
    LETTERS_AS_PDF,
    EMAIL_TYPE
)
from app.dao.notifications_dao import dao_set_created_live_letter_api_notifications_to_pending

from tests.app.db import create_notification, create_service, create_template, create_job


def test_should_only_get_letter_notifications(
    notify_db_session
):
    service = create_service(service_permissions=[LETTER_TYPE])
    pdf_service = create_service(service_name='pdf_service', service_permissions=[LETTERS_AS_PDF])
    pdf_letter_template = create_template(service=pdf_service, template_type=LETTER_TYPE)
    letter_template = create_template(service=service, template_type=LETTER_TYPE)
    sms_template = create_template(service=service)
    email_template = create_template(service=service, template_type=EMAIL_TYPE)
    letter_notification = create_notification(template=letter_template)
    pdf_letter_notification = create_notification(template=pdf_letter_template)
    sms_notification = create_notification(template=sms_template)
    email_notification = create_notification(template=email_template)
    ret = dao_set_created_live_letter_api_notifications_to_pending()

    assert letter_notification.status == NOTIFICATION_PENDING
    assert email_notification.status == NOTIFICATION_CREATED
    assert pdf_letter_notification.status == NOTIFICATION_CREATED
    assert sms_notification.status == NOTIFICATION_CREATED
    assert ret == [letter_notification]


def test_should_ignore_letters_as_pdf(notify_db_session):
    pdf_service = create_service(service_name='pdf service', service_permissions=[LETTER_TYPE, LETTERS_AS_PDF])
    pdf_template = create_template(service=pdf_service, template_type=LETTER_TYPE)
    service = create_service(service_permissions=[LETTER_TYPE])
    template = create_template(service=service, template_type=LETTER_TYPE)

    notification = create_notification(template)
    create_notification(pdf_template)

    all_noti = Notification.query.all()
    assert len(all_noti) == 2

    ret = dao_set_created_live_letter_api_notifications_to_pending()

    assert notification.status == NOTIFICATION_PENDING
    assert ret == [notification]


def test_should_only_get_created_letters(notify_db_session):
    service = create_service(service_permissions=[LETTER_TYPE])
    template = create_template(service=service, template_type=LETTER_TYPE)
    created_noti = create_notification(template, status=NOTIFICATION_CREATED)
    create_notification(template, status=NOTIFICATION_PENDING)
    create_notification(template, status=NOTIFICATION_SENDING)

    ret = dao_set_created_live_letter_api_notifications_to_pending()

    assert ret == [created_noti]


def test_should_only_get_api_letters(notify_db_session):
    service = create_service(service_permissions=[LETTER_TYPE])
    template = create_template(service=service, template_type=LETTER_TYPE)
    job = create_job(template=template)
    api_noti = create_notification(template)
    create_notification(template, job=job)

    ret = dao_set_created_live_letter_api_notifications_to_pending()

    assert ret == [api_noti]


def test_should_only_get_normal_api_letters(notify_db_session):
    service = create_service(service_permissions=[LETTER_TYPE])
    template = create_template(service=service, template_type=LETTER_TYPE)
    live_noti = create_notification(template, key_type=KEY_TYPE_NORMAL)
    create_notification(template, key_type=KEY_TYPE_TEST)

    ret = dao_set_created_live_letter_api_notifications_to_pending()

    assert ret == [live_noti]
