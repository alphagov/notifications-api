from app.schema_validation.definitions import uuid

letter_job_ids = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "list of job ids",
    "type": "object",
    "title": "job_ids",
    "properties": {
        "job_ids": {"type": "array",
                    "items": uuid,
                    "minItems": 1
                    },
    },
    "required": ["job_ids"]
}


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
