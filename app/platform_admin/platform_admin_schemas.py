get_users_list_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "minProperties": 1,
    "properties": {
        "logged_in_start": {"type": ["string", "null"], "format": "date"},
        "logged_in_end": {"type": ["string", "null"], "format": "date"},
        "created_start": {"type": ["string", "null"], "format": "date"},
        "created_end": {"type": ["string", "null"], "format": "date"},
        "take_part_in_research": {"type": ["boolean", "null"]},
    },
    "required": [],
    "additionalProperties": False,
}
