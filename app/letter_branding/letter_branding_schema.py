post_letter_branding_schema = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "POST schema for creating or updating a letter brand",
    "type": "object",
    "properties": {
        "name": {"type": ["string", "null"]},
        "filename": {"type": ["string", "null"]},
    },
    "required": ("name", "filename")
}
