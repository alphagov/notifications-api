from app.schema_validation.definitions import uuid

post_create_template_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST create new email linked file",
    "type": "object",
    "title": "payload for POST /service/<uuid:service_id>/template",
    "properties": {
        "id": uuid,
        "filename": {"type": "string"},
        "linktext": {"type": "string"},
        "service": uuid,
        "retention_period": int,
        "validate_users_email": bool,
        "created_at": {"type": "string", "format": "date-time"},
        "updated_at": {"type": "string", "format": "date-time"},
        "archived_at": {"type": "string", "format": "date-time"},
        "created_by": uuid,
        "parent_folder_id": uuid,
        "postage": {"type": "string", "format": "postage"},
    },
    "allOf": [
        {
            "if": {"properties": {"template_type": {"enum": ["email", "letter"]}}},
            "then": {"required": ["subject"]},
            "required": ["name", "template_type", "content", "service", "created_by"],
        },
    ],
}
