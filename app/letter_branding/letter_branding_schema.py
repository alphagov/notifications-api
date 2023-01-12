from app.schema_validation.definitions import uuid

post_create_letter_branding_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST schema for creating a letter brand",
    "type": "object",
    "properties": {
        "name": {"type": ["string", "null"]},
        "filename": {"type": ["string", "null"]},
        "created_by_id": uuid,
    },
    "required": ["name", "filename"],
}

post_update_letter_branding_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST schema for updating a letter brand",
    "type": "object",
    "properties": {
        "name": {"type": ["string", "null"]},
        "filename": {"type": ["string", "null"]},
        "updated_by_id": uuid,
    },
    "required": ["name", "filename"],
}

post_get_unique_name_for_letter_branding_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST schema for getting unique name for letter branding",
    "type": "object",
    "properties": {
        "name": {"type": "string"},
    },
    "required": ["name"],
}
