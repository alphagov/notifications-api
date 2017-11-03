from app.schema_validation.definitions import uuid


get_inbound_sms_single_response = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "GET inbound sms schema response",
    "type": "object",
    "title": "GET response v2/inbound_sms",
    "properties": {
        "provider_date": {
            "format": "date-time",
            "type": "string",
            "description": "Date+time sent by provider"
        },
        "provider_reference": {"type": ["string", "null"]},
        "user_number": {"type": "string"},
        "created_at": {
            "format": "date-time",
            "type": "string",
            "description": "Date+time created at"
        },
        "service_id": uuid,
        "id": uuid,
        "notify_number": {"type": "string"},
        "content": {"type": "string"},
    },
    "required": [
        "id", "provider_date", "provider_reference",
        "user_number", "created_at", "service_id",
        "notify_number", "content"
    ],
}

get_inbound_sms_response = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "GET list of inbound sms response schema",
    "type": "object",
    "properties": {
        "inbound_sms_list": {
            "type": "array",
            "items": {
                "type": "object",
                "$ref": "#/definitions/inbound_sms"
            }
        },
    },
    "required": ["inbound_sms_list"],
    "definitions": {
        "inbound_sms": get_inbound_sms_single_response
    }
}
