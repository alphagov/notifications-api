from app.schema_validation.definitions import uuid


get_inbound_sms_request = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "schema for query parameters allowed when getting list of received text messages",
    "type": "object",
    "properties": {
        "older_than": uuid,
    },
    "additionalProperties": False,
}


get_inbound_sms_single_response = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "GET inbound sms schema response",
    "type": "object",
    "title": "GET response v2/inbound_sms",
    "properties": {
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
        "id", "user_number", "created_at", "service_id",
        "notify_number", "content"
    ],
    "additionalProperties": False,
}

get_inbound_sms_response = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "GET list of inbound sms response schema",
    "type": "object",
    "properties": {
        "received_text_messages": {
            "type": "array",
            "items": {
                "type": "object",
                "$ref": "#/definitions/inbound_sms"
            }
        },
        "links": {
            "type": "object",
            "properties": {
                "current": {
                    "type": "string"
                },
                "next": {
                    "type": "string"
                }
            },
            "additionalProperties": False,
            "required": ["current"]
        }
    },
    "required": ["received_text_messages", "links"],
    "definitions": {
        "inbound_sms": get_inbound_sms_single_response
    },
    "additionalProperties": False,
}
