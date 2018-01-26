from app import DATETIME_FORMAT
from app.models import LETTER_TYPE
from app.schema_validation.definitions import uuid

template = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "template schema",
    "type": "object",
    "title": "notification content",
    "properties": {
        "id": uuid,
        "version": {"type": "integer"},
        "name": {"type": "string"}
    },
    "required": ["id", "version", "name"]
}

notification_for_service_no_content = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "GET notification for service schema",
    "type": "object",
    "title": "response service/{service_id}/notifications",
    "properties": {
        "id": {"type": ["string", "null"]},
        "recipient": {"type": ["string", "null"]},
        "type": {"enum": ["sms", "letter", "email"]},
        "status": {"type": "string"},
        "template": template,
        "created_at": {"type": "string"},
        "sent_at": {"type": ["string", "null"]},
        "completed_at": {"type": ["string", "null"]},
        "job": {"type": ["string", "null"]},
        "sent_by": {"type": ["string", "null"]},
    },
    "required": [
        # technically, all keys are required since we always have all of them
        "id", "recipient",
        "type", "status", "template",
        "created_at", "sent_at", "completed_at"
    ]
}


def build_notification_for_service(notification):
    return {
        "id": notification.id,
        "recipient": notification.to,
        "type": notification.notification_type,
        "status": _build_status(notification),
        "template": _build_template(notification),
        "created_at": notification.created_at.strftime(DATETIME_FORMAT),
        "sent_at": notification.sent_at.strftime(DATETIME_FORMAT) if notification.sent_at else None,
        "completed_at": notification.completed_at(),
        "job": notification.job.original_file_name if notification.job_id else None,
        "sent_by": notification.sent_by
    }


def _build_status(notification):
    return notification.get_letter_status() if notification.notification_type == LETTER_TYPE else notification.status


def _build_template(notification):
    return {
        "id": notification.template.id,
        "version": notification.template.version,
        "name": notification.template.name
    }
