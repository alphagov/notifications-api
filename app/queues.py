# app/queues.py

from flask import current_app

from app.config import QueueNames


def get_message_group_id_for_queue(
    queue_name: QueueNames,
    service_id: str,
    notification_type: str | None = None,
    origin: str | None = None,  # "api" or "dashboard"
    key_type: str | None = None,  # normal, team, test
    emergency: bool | None = None,  # True/False
) -> str:
    if queue_name in (QueueNames.JOBS, QueueNames.DATABASE):
        # service + notif type
        return f"{service_id}#{notification_type}"

    if queue_name in (
        QueueNames.SEND_SMS,
        QueueNames.SEND_EMAIL,
        QueueNames.CREATE_LETTERS_PDF,
    ):
        # service + origin + key type because these are shared with API requests
        # emergency optional
        parts = [service_id]

        if origin:
            parts.append(origin)

        if key_type:
            parts.append(key_type)

        if emergency:
            parts.append("emergency")

        return "#".join(parts)

    # default to per service for now, this includes:
    # callbacks, antivirus, scheduled tasks, reporting, retry, etc.
    return str(service_id)


def get_queue_group_id(request):
    group_id = None
    if hasattr(request, "headers") and request.headers:
        group_id = request.headers.get("MessageGroupId")

    return group_id


def log_queue_details(request, function_name, queue_name):
    group_id = get_queue_group_id(request)

    current_app.logger.info(
        "Fair queue DEBUG - operation: %s, queue name %s and group_id: %s",
        function_name,
        queue_name,
        group_id,
        extra={"message_group_id": group_id},
    )
