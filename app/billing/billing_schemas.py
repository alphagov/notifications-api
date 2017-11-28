create_or_update_free_sms_fragment_limit_schema = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "POST annual billing schema",
    "type": "object",
    "title": "Create",
    "properties": {
        "free_sms_fragment_limit": {"type": "integer", "minimum": 1},
    },
    "required": ["free_sms_fragment_limit"]
}
