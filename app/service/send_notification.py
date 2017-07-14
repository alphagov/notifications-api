from app.celery import QueueNames
from app.notifications.validators import (
    check_service_over_daily_message_limit,
    validate_and_format_recipient,
    validate_template,
)
from app.notifications.process_notifications import (
    create_content_for_notification,
    persist_notification,
    send_notification_to_queue,
)
from app.models import (
    KEY_TYPE_NORMAL,
    PRIORITY,
    SMS_TYPE,
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
        notification_type=template.template_type
    )

    validate_created_by(service, post_data['created_by'])

    notification = persist_notification(
        template_id=template.id,
        template_version=template.version,
        recipient=post_data['to'],
        service=service,
        personalisation=personalisation,
        notification_type=template.template_type,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL,
        created_by_id=post_data['created_by']
    )

    queue_name = QueueNames.PRIORITY if template.process_type == PRIORITY else None
    send_notification_to_queue(
        notification=notification,
        research_mode=service.research_mode,
        queue=queue_name
    )

    return {'id': str(notification.id)}
