from app.schema_validation.definitions import uuid

post_create_organisation_schema = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "POST organisation schema",
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "active": {"type": ["boolean", "null"]}
    },
    "required": ["name"]
}

post_update_organisation_schema = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "POST organisation schema",
    "type": "object",
    "properties": {
        "name": {"type": ["string", "null"]},
        "active": {"type": ["boolean", "null"]}
    },
    "required": []
}

post_link_service_to_organisation_schema = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "POST link service to organisation schema",
    "type": "object",
    "properties": {
        "service_id": uuid
    },
    "required": ["service_id"]
}
