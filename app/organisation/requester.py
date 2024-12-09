from flask import current_app

from app.config import QueueNames
from app.constants import KEY_TYPE_NORMAL
from app.dao.services_dao import dao_fetch_service_by_id
from app.notifications.process_notifications import (
    persist_notification,
    send_notification_to_queue,
)


def send_go_live_request_receipt_to_requester(
    organisation,
    service,
    template,
    approver_users,
):
    reply_to_text = current_app.config["NOTIFY_SUPPORT_EMAIL_ADDRESS"]
    personalisation = {
        "service_name": service.name,
        "name": service.go_live_user.name,
        "organisation_name": organisation.name,
        "organisation_team_member_names": [f"{user.name}" for user in approver_users],
    }
    notify_service = dao_fetch_service_by_id(current_app.config["NOTIFY_SERVICE_ID"])

    notification = persist_notification(
        template_id=template.id,
        template_version=template.version,
        recipient=service.go_live_user.email_address,
        service=notify_service,
        personalisation=personalisation,
        notification_type=template.template_type,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL,
        reply_to_text=reply_to_text,
    )
    send_notification_to_queue(notification, queue=QueueNames.NOTIFY)
