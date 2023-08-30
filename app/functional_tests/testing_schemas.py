create_functional_test_users_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "schema for creating functional test users",
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "required": True},
            "email_address": {"type": "string", "format": "email_address", "required": True},
            "mobile_number": {"type": "string", "required": True},
            "auth_type": {"type": "string", "required": True},
            "password": {"type": "string", "required": True},
            "state": {"type": "string", "required": True},
            "permissions": {"type": "array", "items": {"type": "string"}, "required": True},
            "service_id": {"type": "string", "required": True},
            "organisation_id": {"type": "string", "required": False},
        },
    },
}
