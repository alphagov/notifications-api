from app.schema_validation.definitions import uuid, https_url

service_inbound_api = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "POST service inbound api schema",
    "type": "object",
    "title": "Create service inbound api",
    "properties": {
        "url": https_url,
        "bearer_token": {"type": "string", "minLength": 10},
        "updated_by_id": uuid
    },
    "required": ["url", "bearer_token", "updated_by_id"]
}

update_service_inbound_api_schema = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "POST service inbound api schema",
    "type": "object",
    "title": "Create service inbound api",
    "properties": {
        "url": https_url,
        "bearer_token": {"type": "string", "minLength": 10},
        "updated_by_id": uuid
    },
    "required": ["updated_by_id"]
}
