from app.schema_validation.definitions import uuid

post_create_letter_attachment_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST schema for getting letter_attachment",
    "type": "object",
    "properties": {
        "upload_id": uuid,
        "created_by_id": uuid,
        "original_filename": {"type": "string"},
        "page_count": {"type": "integer"},
        "template_id": uuid,
    },
    "required": ["upload_id", "created_by_id", "original_filename", "page_count", "template_id"],
}
