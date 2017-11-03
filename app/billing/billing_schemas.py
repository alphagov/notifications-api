from app.schema_validation.definitions import uuid, https_url


create_or_update_free_sms_fragment_limit_schema = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "POST annual billing schema",
    "type": "object",
    "title": "Create",
    "properties": {
        "free_sms_fragment_limit": {"type": "integer", "minimum": 1},
        "financial_year_start": {"type": "integer", "minimum": 2016}
    },
    "required": ["free_sms_fragment_limit"]
}
