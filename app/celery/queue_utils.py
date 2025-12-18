from flask import current_app

from app.config import QueueNames

QUEUE_GROUPING_RULES: dict[str, tuple[str, ...]] = {
    QueueNames.DATABASE: ("service_id", "notification_type"),
    QueueNames.SEND_SMS: ("service_id", "origin", "key_type"),
    QueueNames.SEND_EMAIL: ("service_id", "origin", "key_type"),
    QueueNames.SEND_LETTER: ("service_id", "origin", "key_type"),
    QueueNames.JOBS: ("service_id", "notification_type", "origin"),
    QueueNames.CREATE_LETTERS_PDF: ("service_id", "key_type", "origin"),
    QueueNames.LETTERS: ("service_id", "key_type"),
    QueueNames.CALLBACKS: ("service_id", "notification_type"),
    QueueNames.REPORT_REQUESTS_NOTIFICATIONS: ("service_id",),
}


def get_message_group_id_for_queue(
    *,
    queue_name: QueueNames,
    service_id: str | None = None,
    notification_type: str | None = None,
    origin: str | None = None,
    key_type: str | None = None,
) -> dict[str, str]:
    if not current_app.config.get("ENABLE_SQS_FAIR_GROUPING", False):
        return {}

    grouping_fields = QUEUE_GROUPING_RULES.get(str(queue_name))

    if not grouping_fields:
        return {}

    values = {
        "service_id": service_id,
        "notification_type": notification_type,
        "origin": origin,
        "key_type": key_type,
    }

    parts: list[str] = []
    for field in grouping_fields:
        value = values.get(field)
        if value:
            parts.append(value)

    if not parts:
        return {}

    return {"MessageGroupId": "#".join(parts)}
