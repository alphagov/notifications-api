from app.constants import NOTIFICATION_REPORT

add_report_request_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "Schema for creating a report request",
    "type": "object",
    "properties": {
        "user_id": {"type": "string", "format": "uuid"},
        "report_type": {"enum": [NOTIFICATION_REPORT]},
        "notification_type": {"enum": ["email", "sms", "letter"]},
        "notification_status": {"enum": ["all", "sending", "delivered", "failed"]},
    },
    "required": ["user_id", "report_type"],
    "additionalProperties": False,
}
