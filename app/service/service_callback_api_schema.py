from app.schema_validation.definitions import https_url, uuid

create_service_callback_api_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST service callback/inbound api schema",
    "type": "object",
    "title": "Create service callback/inbound api",
    "properties": {
        "url": https_url,
        "bearer_token": {"type": "string", "minLength": 10},
        "updated_by_id": uuid,
        "callback_type": {"type": "string"},
    },
    "required": ["url", "bearer_token", "updated_by_id"],
}

update_service_callback_api_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST service callback/inbound api schema",
    "type": "object",
    "title": "Create service callback/inbound api",
    "properties": {
        "url": https_url,
        "bearer_token": {"type": "string", "minLength": 10},
        "updated_by_id": uuid,
        "callback_type": {"type": "string"},
    },
    "required": ["updated_by_id"],
}
