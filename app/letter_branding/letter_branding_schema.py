post_letter_branding_schema = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "POST schema for creating or updating a letter brand",
    "type": "object",
    "properties": {
        "name": {"type": ["string", "null"]},
        "filename": {"type": ["string", "null"]},
        "domain": {"type": ["string", "null"]},
    },
    "required": ("name", "filename", "domain"),
    # Typically we allow additional properties but we don't want to update letter_branding platform_admin,
    # this can handle this without adding extra code in the rest endpoint.
    "additionalProperties": False
}
