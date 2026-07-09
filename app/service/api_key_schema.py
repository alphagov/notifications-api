from app.schema_validation.definitions import uuid

post_revoke_api_key_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST schema for revoking an API key",
    "type": "object",
    "properties": {
        "created_by": uuid,
    },
    "required": [],
    "additionalProperties": False,
}
