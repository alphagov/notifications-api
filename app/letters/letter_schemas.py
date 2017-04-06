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
