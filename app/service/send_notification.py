from app.config import QueueNames
from app.dao.service_email_reply_to_dao import dao_get_reply_to_by_id
from app.dao.service_sms_sender_dao import dao_get_service_sms_senders_by_id
from app.notifications.validators import (
    check_service_over_daily_message_limit,
    validate_and_format_recipient,
    validate_template
)
from app.notifications.process_notifications import (
    persist_notification,
    send_notification_to_queue
)
from app.models import (
    KEY_TYPE_NORMAL,
    SMS_TYPE,
    EMAIL_TYPE,
)
from app.dao.services_dao import dao_fetch_service_by_id
from app.dao.templates_dao import dao_get_template_by_id_and_service_id
from app.dao.users_dao import get_user_by_id
from app.v2.errors import BadRequestError


def validate_created_by(service, created_by_id):
    user = get_user_by_id(created_by_id)
    if service not in user.services:
        message = 'Can’t create notification - {} is not part of the "{}" service'.format(
            user.name,
            service.name
        )
        raise BadRequestError(message=message)


def send_one_off_notification(service_id, post_data):
    service = dao_fetch_service_by_id(service_id)
    template = dao_get_template_by_id_and_service_id(
        template_id=post_data['template_id'],
        service_id=service_id
    )

    personalisation = post_data.get('personalisation', None)

    validate_template(template.id, personalisation, service, template.template_type)

    check_service_over_daily_message_limit(KEY_TYPE_NORMAL, service)

    validate_and_format_recipient(
        send_to=post_data['to'],
        key_type=KEY_TYPE_NORMAL,
        service=service,
        notification_type=template.template_type,
        allow_whitelisted_recipients=False,
    )

    validate_created_by(service, post_data['created_by'])

    sender_id = post_data.get('sender_id', None)
    reply_to = get_reply_to_text(
        notification_type=template.template_type,
        sender_id=sender_id,
        service=service,
        template=template
    )
    notification = persist_notification(
        template_id=template.id,
        template_version=template.version,
        recipient=post_data['to'],
        service=service,
        personalisation=personalisation,
        notification_type=template.template_type,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL,
        created_by_id=post_data['created_by'],
        reply_to_text=reply_to
    )

    send_notification_to_queue(
        notification=notification,
        research_mode=service.research_mode,
        queue=QueueNames.PRIORITY
    )

    return {'id': str(notification.id)}


def get_reply_to_text(notification_type, sender_id, service, template):
    reply_to = None
    if sender_id:
        if notification_type == EMAIL_TYPE:
            reply_to = dao_get_reply_to_by_id(service.id, sender_id).email_address
        elif notification_type == SMS_TYPE:
            reply_to = dao_get_service_sms_senders_by_id(service.id, sender_id).get_reply_to_text()
    else:
        reply_to = template.get_reply_to_text()
    return reply_to
