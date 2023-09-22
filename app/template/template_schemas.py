from app.constants import TEMPLATE_PROCESS_TYPE, TEMPLATE_TYPES, LetterLanguageOptions
from app.schema_validation.definitions import nullable_uuid, uuid

post_create_template_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST create new template",
    "type": "object",
    "title": "payload for POST /service/<uuid:service_id>/template",
    "properties": {
        "name": {"type": "string"},
        "template_type": {"enum": TEMPLATE_TYPES},
        "service": uuid,
        "process_type": {"enum": TEMPLATE_PROCESS_TYPE},
        "content": {"type": "string"},
        "subject": {"type": "string"},
        "created_by": uuid,
        "parent_folder_id": uuid,
        "postage": {"type": "string", "format": "postage"},
    },
    "if": {"properties": {"template_type": {"enum": ["email", "letter"]}}},
    "then": {"required": ["subject"]},
    "required": ["name", "template_type", "content", "service", "created_by"],
}

post_update_template_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST update existing template",
    "type": "object",
    "title": "payload for POST /service/<uuid:service_id>/template/<uuid:template_id>",
    "properties": {
        "id": uuid,
        "name": {"type": "string"},
        "template_type": {"enum": TEMPLATE_TYPES},
        "service": uuid,
        "process_type": {"enum": TEMPLATE_PROCESS_TYPE},
        "content": {"type": "string"},
        "subject": {"type": "string"},
        "postage": {"type": "string", "format": "postage"},
        "reply_to": nullable_uuid,
        "created_by": uuid,
        "archived": {"type": "boolean"},
        "current_user": uuid,
        "letter_languages": {"type": "string", "enum": [i.value for i in LetterLanguageOptions]},
        "letter_welsh_subject": {},
        "letter_welsh_content": {},
    },
    "if": {
        "properties": {"letter_languages": {"const": LetterLanguageOptions.english.value}},
    },
    "then": {
        "properties": {
            "letter_welsh_subject": {"type": "null"},
            "letter_welsh_content": {"type": "null"},
        }
    },
    "else": {
        "if": {
            "properties": {"letter_languages": {"const": LetterLanguageOptions.welsh_then_english.value}},
        },
        "then": {
            "properties": {
                "letter_welsh_subject": {"type": "string"},
                "letter_welsh_content": {"type": "string"},
            },
            "required": ["letter_welsh_subject", "letter_welsh_content"],
        },
    },
}
