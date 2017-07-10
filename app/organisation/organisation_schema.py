post_create_organisation_schema = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "POST schema for getting organisation",
    "type": "object",
    "properties": {
        "colour": {"type": ["string", "null"]},
        "name": {"type": ["string", "null"]},
        "logo": {"type": ["string", "null"]}
    },
    "required": ["logo"]
}

post_update_organisation_schema = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "POST schema for getting organisation",
    "type": "object",
    "properties": {
        "colour": {"type": ["string", "null"]},
        "name": {"type": ["string", "null"]},
        "logo": {"type": ["string", "null"]}
    },
    "required": []
}
