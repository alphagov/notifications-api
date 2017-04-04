from app.models import TEMPLATE_TYPES
from app.v2.template.template_schemas import get_template_by_id_response as template


get_all_template_request = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "request schema for parameters allowed when getting all templates",
    "type": "object",
    "properties": {
        "type": {"enum": TEMPLATE_TYPES}
    },
    "additionalProperties": False,
}

get_all_template_response = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "GET response schema when getting all templates",
    "type": "object",
    "properties": {
        "templates": {
            "type": "array",
            "items": {
                "type": "object",
                "$ref": "#/definitions/template"
            }
        }
    },
    "required": ["templates"],
    "definitions": {
        "template": template
    }
}
