from app.models import TEMPLATE_TYPES
from app.schema_validation.definitions import uuid


get_template_by_id_request = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "schema for parameters allowed when getting template by id",
    "type": "object",
    "properties": {
        "id": uuid,
        "version": {"type": ["integer", "null"], "minimum": 1}
    },
    "required": ["id"],
    "additionalProperties": False,
}

get_template_by_id_response = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "GET template by id schema response",
    "type": "object",
    "title": "reponse v2/template",
    "properties": {
        "id": uuid,
        "type": {"enum": TEMPLATE_TYPES},
        "created_at": {
            "format": "date-time",
            "type": "string",
            "description": "Date+time created"
        },
        "updated_at": {
            "format": "date-time",
            "type": "string",
            "description": "Date+time updated"
        },
        "created_by": {"type": "string"},
        "version": {"type": "integer"},
        "body": {"type": "string"},
        "subject": {"type": ["string", "null"]}
    },
    "required": ["id", "type", "created_at", "updated_at", "version", "created_by", "body"]
}
