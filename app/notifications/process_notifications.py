from datetime import datetime

from flask import current_app
from notifications_utils.renderers import PassThrough
from notifications_utils.template import Template

from app import DATETIME_FORMAT
from app.celery import provider_tasks
from app.dao.notifications_dao import dao_create_notification, dao_delete_notifications_and_history_by_id
from app.models import SMS_TYPE, Notification, KEY_TYPE_TEST, EMAIL_TYPE
from app.notifications.validators import check_sms_content_char_count
from app.v2.errors import BadRequestError


def create_content_for_notification(template, personalisation):
    template_object = Template(
        template.__dict__,
        personalisation,
        renderer=PassThrough()
    )
    check_placeholders(template_object)

    if template_object.template_type == SMS_TYPE:
        check_sms_content_char_count(template_object.replaced_content_count)
    return template_object


def check_placeholders(template_object):
    if template_object.missing_data:
        message = 'Template missing personalisation: {}'.format(", ".join(template_object.missing_data))
        raise BadRequestError(fields=[{'template': message}], message=message)

    if template_object.additional_data:
        message = 'Template personalisation not needed for template: {}'.format(
            ", ".join(template_object.additional_data))
        raise BadRequestError(fields=[{'template': message}], message=message)


def persist_notification(template_id,
                         template_version,
                         recipient,
                         service_id,
                         personalisation,
                         notification_type,
                         api_key_id,
                         key_type,
                         created_at=None,
                         job_id=None,
                         job_row_number=None,
                         reference=None):
    notification = Notification(
        template_id=template_id,
        template_version=template_version,
        to=recipient,
        service_id=service_id,
        personalisation=personalisation,
        notification_type=notification_type,
        api_key_id=api_key_id,
        key_type=key_type,
        created_at=created_at or datetime.utcnow().strftime(DATETIME_FORMAT),
        job_id=job_id,
        job_row_number=job_row_number,
        client_reference=reference
    )
    dao_create_notification(notification)
    return notification


def send_notification_to_queue(notification, research_mode):
    try:
        research_mode = research_mode or notification.key_type == KEY_TYPE_TEST
        if notification.notification_type == SMS_TYPE:
            provider_tasks.deliver_sms.apply_async(
                [str(notification.id)],
                queue='send-sms' if not research_mode else 'research-mode'
            )
        if notification.notification_type == EMAIL_TYPE:
            provider_tasks.deliver_email.apply_async(
                [str(notification.id)],
                queue='send-email' if not research_mode else 'research-mode'
            )
    except Exception:
        current_app.logger.exception("Failed to send to SQS exception")
        dao_delete_notifications_and_history_by_id(notification.id)
        raise

    current_app.logger.info(
        "{} {} created at {}".format(notification.notification_type, notification.id, notification.created_at)
    )
