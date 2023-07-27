from app.constants import TEMPLATE_TYPES
from app.schema_validation.definitions import personalisation, uuid

get_template_by_id_response = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "GET template by id schema response",
    "type": "object",
    "title": "reponse v2/template",
    "properties": {
        "id": uuid,
        "type": {"enum": TEMPLATE_TYPES},
        "created_at": {"format": "date-time", "type": "string", "description": "Date+time created"},
        "updated_at": {"format": "date-time", "type": ["string", "null"], "description": "Date+time updated"},
        "created_by": {"type": "string"},
        "version": {"type": "integer"},
        "body": {"type": "string"},
        "subject": {"type": ["string", "null"]},
        "name": {"type": "string"},
        "postage": {"type": "string", "format": "postage"},
    },
    "required": ["id", "type", "created_at", "updated_at", "version", "created_by", "body", "name"],
}

post_template_preview_request = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST template schema",
    "type": "object",
    "title": "POST v2/template/{id}/preview",
    "properties": {"id": uuid, "personalisation": personalisation},
    "required": ["id"],
}

post_template_preview_response = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST template preview schema response",
    "type": "object",
    "title": "reponse v2/template/{id}/preview",
    "properties": {
        "id": uuid,
        "type": {"enum": TEMPLATE_TYPES},
        "version": {"type": "integer"},
        "body": {"type": "string"},
        "subject": {"type": ["string", "null"]},
        "postage": {"type": "string", "format": "postage"},
        "html": {"type": ["string", "null"]},
    },
    "required": ["id", "type", "version", "body"],
    "additionalProperties": False,
}


def create_post_template_preview_response(template, template_object):
    return {
        "id": template.id,
        "type": template.template_type,
        "version": template.version,
        "body": template_object.content_with_placeholders_filled_in,
        "html": getattr(template_object, "html_body", None),
        "subject": getattr(template_object, "subject", None),
        "postage": template.postage,
    }
