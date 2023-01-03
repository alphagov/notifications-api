post_letter_branding_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST schema for creating or updating a letter brand",
    "type": "object",
    "properties": {
        "name": {"type": ["string", "null"]},
        "filename": {"type": ["string", "null"]},
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
