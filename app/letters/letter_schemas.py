letter_references = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "list of letter notification references",
    "type": "object",
    "title": "references",
    "properties": {
        "references": {
            "type": "array",
            "items": {
                "type": "string",
                "pattern": "^[0-9A-Z]{16}$"
            },
            "minItems": 1
        },
    },
    "required": ["references"]
}
