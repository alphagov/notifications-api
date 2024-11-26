protected_sender_request = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "protected sender id request schema",
    "type": "object",
    "title": "Protected sender id check",
    "properties": {
        "sender_id": {"type": "string", "minLength": 1},
        "organisation_id": {"type": "string", "format": "uuid"},
    },
    "required": ["sender_id"],
}
