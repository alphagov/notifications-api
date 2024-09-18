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
