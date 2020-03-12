from app.schema_validation.definitions import uuid

create_service_contact_list_schema = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "POST create service contact list schema",
    "type": "object",
    "title": "Create service contact list",
    "properties": {
        "id": uuid,
        "original_file_name": {"type": "string"},
        "row_count": {"type": "integer"},
        "template_type": {"enum": ['email', 'sms']},
        "created_by": uuid
    },
    "required": ["id", "original_file_name", "row_count", "template_type", "created_by"]
}
