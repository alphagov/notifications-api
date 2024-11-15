from app.constants import EMAIL_AUTH_TYPE, SMS_AUTH_TYPE

service_join_request_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "Schema for creating a service join request",
    "type": "object",
    "properties": {
        "requester_id": {"type": "string", "format": "uuid"},
        "contacted_user_ids": {"type": "array", "minItems": 1, "items": {"type": "string", "format": "uuid"}},
        "reason": {"type": ["string", "null"], "description": "Optional reason for the request"},
    },
    "required": ["requester_id", "contacted_user_ids"],
    "additionalProperties": False,
}

service_join_request_update_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "Schema for updating a service join request",
    "type": "object",
    "properties": {
        "permissions": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": [
                    "manage_users",
                    "manage_templates",
                    "manage_settings",
                    "send_texts",
                    "send_emails",
                    "send_letters",
                    "manage_api_keys",
                    "view_activity",
                ],
            },
            "description": "List of permissions being granted or modified",
        },
        "folder_permissions": {"type": "array", "items": {"type": "string"}},
        "status_changed_by_id": {"type": "string", "format": "uuid"},
        "status": {
            "type": "string",
            "enum": ["pending", "approved", "rejected", "cancelled"],
            "description": "The new status of the join request",
        },
        "reason": {"type": ["string", "null"], "description": "Optional reason for the status change"},
        "auth_type": {"enum": [EMAIL_AUTH_TYPE, SMS_AUTH_TYPE]},
    },
    "required": ["status_changed_by_id", "status"],
    "additionalProperties": False,
    "minProperties": 2,
}
