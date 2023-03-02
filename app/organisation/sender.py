from flask import current_app

from app.config import QueueNames
from app.constants import KEY_TYPE_NORMAL
from app.dao.organisation_dao import dao_get_users_for_organisation
from app.dao.services_dao import dao_fetch_service_by_id
from app.notifications.process_notifications import (
    persist_notification,
    send_notification_to_queue,
)


def send_notification_to_organisation_users(
    *, organisation, template, reply_to_text, personalisation=None, include_user_fields=None
):
    personalisation = personalisation or {}
    include_user_fields = include_user_fields or []
    active_users = dao_get_users_for_organisation(organisation.id)
    notify_service = dao_fetch_service_by_id(current_app.config["NOTIFY_SERVICE_ID"])

    for user in active_users:
        personalisation = personalisation | {field: getattr(user, field) for field in include_user_fields}
        notification = persist_notification(
            template_id=template.id,
            template_version=template.version,
            recipient=user.email_address,
            service=notify_service,
            personalisation=personalisation,
            notification_type=template.template_type,
            api_key_id=None,
            key_type=KEY_TYPE_NORMAL,
            reply_to_text=reply_to_text,
        )
        send_notification_to_queue(notification, queue=QueueNames.NOTIFY)
