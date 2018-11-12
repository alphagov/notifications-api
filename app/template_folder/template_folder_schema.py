from app.schema_validation.definitions import nullable_uuid, uuid

post_create_template_folder_schema = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "POST schema for getting template_folder",
    "type": "object",
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "parent_id": nullable_uuid
    },
    "required": ["name", "parent_id"]
}

post_update_template_folder_schema = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "POST schema for updating template_folder",
    "type": "object",
    "properties": {
        "name": {"type": "string", "minLength": 1},
    },
    "required": ["name"]
}

post_move_template_folder_schema = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "POST schema for renaming template_folder",
    "type": "object",
    "properties": {
        "templates": {"type": "array", "items": uuid},
        "folders": {"type": "array", "items": uuid},
    },
    "required": ["templates", "folders"]
}
