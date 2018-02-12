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
