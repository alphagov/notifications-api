from flask import current_app
from notifications_utils.renderers import PassThrough
from notifications_utils.template import Template

from app.celery import provider_tasks
from app.dao.notifications_dao import dao_create_notification, dao_delete_notifications_and_history_by_id
from app.errors import InvalidRequest
from app.models import SMS_TYPE, Notification, KEY_TYPE_TEST, EMAIL_TYPE
from app.notifications.validators import check_sms_content_char_count
from app.v2.errors import BadRequestError


def create_content_for_notification(template, personalisation):
    template_object = Template(
        template.__dict__,
        personalisation,
        renderer=PassThrough()
    )
    if template_object.missing_data:
        message = 'Missing personalisation: {}'.format(", ".join(template_object.missing_data))
        errors = {'template': [message]}
        raise BadRequestError(errors)

    if template_object.additional_data:
        message = 'Personalisation not needed for template: {}'.format(", ".join(template_object.additional_data))
        errors = {'template': [message]}
        raise BadRequestError(fields=errors)

    if template_object.template_type == SMS_TYPE:
        check_sms_content_char_count(template_object.replaced_content_count)
    return template_object


def persist_notification(template_id,
                         template_version,
                         recipient,
                         service_id,
                         personalisation,
                         notification_type,
                         api_key_id,
                         key_type):
    notification = Notification.from_v2_api_request(template_id,
                                                    template_version,
                                                    recipient,
                                                    service_id,
                                                    personalisation,
                                                    notification_type,
                                                    api_key_id,
                                                    key_type)
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
    except Exception as e:
        current_app.logger.exception("Failed to send to SQS exception")
        dao_delete_notifications_and_history_by_id(notification.id)
        raise InvalidRequest(message="Internal server error", status_code=500)

    current_app.logger.info(
        "{} {} created at {}".format(notification.notification_type, notification.id, notification.created_at)
    )
