from app.schema_validation.definitions import (uuid, personalisation)

post_sms_request = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "POST sms notification schema",
    "type": "object",
    "title": "POST v2/notifications/sms",
    "properties": {
        "reference": {"type": "string"},
        "phone_number": {"type": "string", "format": "sms"},
        "template_id": uuid,
        "personalisation": personalisation
    },
    "required": ["phone_number", "template_id"]
}

content = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "POST sms notification response schema",
    "type": "object",
    "title": "notification content",
    "properties": {
        "body": {"type": "string"},
        "from_number": {"type": "string"}
    },
    "required": ["body"]
}

# this may belong in a templates module
template = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "POST sms notification response schema",
    "type": "object",
    "title": "notification content",
    "properties": {
        "id": uuid,
        "version": {"type": "integer"},
        "uri": {"type": "string"}
    },
    "required": ["id", "version", "uri"]
}

post_sms_response = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "POST sms notification response schema",
    "type": "object",
    "title": "response v2/notifications/sms",
    "properties": {
        "id": uuid,
        "reference": {"type": "string"},
        "content": content,
        "uri": {"type": "string"},
        "template": template
    },
    "required": ["id", "content", "uri", "template"]
}
