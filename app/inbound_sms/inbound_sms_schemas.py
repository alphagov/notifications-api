get_inbound_sms_for_service_schema = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "schema for parameters allowed when searching for to field=",
    "type": "object",
    "properties": {
        "phone_number": {"type": "string", "format": "phone_number"},
        "limit": {"type": ["integer", "null"], "minimum": 1}
    }
}
