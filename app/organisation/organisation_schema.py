post_organisation_schema = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "POST schema for getting organisation",
    "type": "object",
    "properties": {
        "colour": {"type": ["string", "null"], "format": "string"},
        "name": {"type": ["string", "null"], "minimum": 1},
        "logo": {"type": ["string", "null"], "minimum": 1}
    },
    "required": ["logo"]
}
