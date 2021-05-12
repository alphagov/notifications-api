post_create_webauthn_credential_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST webauthn_credential schema",
    "type": "object",
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "credential_data": {"type": "string", "minLength": 1},
        "registration_response": {"type": "string", "minLength": 1},
    },
    "required": ["name", "credential_data", "registration_response"],
    "additionalProperties": False
}

post_update_webauthn_credential_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST update webauthn_credential schema",
    "type": "object",
    "properties": {
        "name": {"type": "string", "minLength": 1},
    },
    "required": ["name"],
    "additionalProperties": False
}
