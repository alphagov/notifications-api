from app.models import TEMPLATE_TYPES
from app.schema_validation.definitions import uuid
from app.v2.template_schema import template


get_all_template_request = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "request schema for parameters allowed when getting all templates",
    "type": "object",
    "properties": {
        "type": {"enum": TEMPLATE_TYPES},
        "older_than": uuid
    },
    "additionalProperties": False,
}

get_all_template_response = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "GET response schema when getting all templates",
    "type": "object",
    "properties": {
        "links": {
            "type": "object",
            "properties": {
                "current": {
                    "type": "string",
                    "format": "uri"
                },
                "next": {
                    "type": "string",
                    "format": "uri"
                }
            },
            "additionalProperties": False,
            "required": ["current"],
        },
        "templates": {
            "type": "array",
            "items": {
                "type": "object",
                "$ref": "#/definitions/template"
            }
        }
    },
    "required": ["links", "templates"],
    "definitions": {
        "template": template
    }
}
