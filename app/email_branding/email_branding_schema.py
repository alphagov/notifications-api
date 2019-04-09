from app.models import BRANDING_TYPES

post_create_email_branding_schema = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "POST schema for getting email_branding",
    "type": "object",
    "properties": {
        "colour": {"type": ["string", "null"]},
        "name": {"type": "string"},
        "text": {"type": ["string", "null"]},
        "logo": {"type": ["string", "null"]},
        "domain": {"type": ["string", "null"]},
        "brand_type": {"enum": BRANDING_TYPES},
    },
    "required": ["name"]
}

post_update_email_branding_schema = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "POST schema for getting email_branding",
    "type": "object",
    "properties": {
        "colour": {"type": ["string", "null"]},
        "name": {"type": ["string", "null"]},
        "text": {"type": ["string", "null"]},
        "logo": {"type": ["string", "null"]},
        "domain": {"type": ["string", "null"]},
        "brand_type": {"enum": BRANDING_TYPES},
    },
    "required": []
}
