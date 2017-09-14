add_service_email_reply_to_request = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "POST service email reply to address",
    "type": "object",
    "title": "Add new email reply to address for service",
    "properties": {
        "email_address": {"type": "string", "format": "email_address"},
        "is_default": {"type": "boolean"}
    },
    "required": ["email_address"]
}
