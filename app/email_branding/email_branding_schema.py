from app.models import BRANDING_TYPES

post_create_email_branding_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST schema for getting email_branding",
    "type": "object",
    "properties": {
        "colour": {"type": ["string", "null"]},
        "name": {"type": "string"},
        "alt_text": {"type": ["string", "null"]},
        "text": {"type": ["string", "null"]},
        "logo": {"type": ["string", "null"]},
        "brand_type": {"enum": BRANDING_TYPES},
        "created_by": {"type": ["string"], "required": False},
    },
    "required": ["name"],
}

post_update_email_branding_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST schema for getting email_branding",
    "type": "object",
    "properties": {
        "colour": {"type": ["string", "null"]},
        "name": {"type": "string"},
        "alt_text": {"type": ["string", "null"]},
        "text": {"type": ["string", "null"]},
        "logo": {"type": ["string", "null"]},
        "brand_type": {"enum": BRANDING_TYPES},
        "updated_by": {"type": ["string"], "required": False},
    },
    "required": [],
}
post_get_email_branding_name_for_alt_text_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST schema for getting email_branding",
    "type": "object",
    "properties": {
        "alt_text": {"type": "string"},
    },
    "required": ["alt_text"],
}
