from app.schema_validation.definitions import uuid

post_create_template_email_files_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST create new email linked file",
    "type": "object",
    "title": "payload for POST /service/<uuid:service_id>/template",
    "properties": {
        "id": uuid,
        "filename": {"type": "string"},
        "link_text": {"type": "string"},
        "service": uuid,
        "retention_period": {"type": "integer"},
        "validate_users_email": {"type": "boolean"},
        "template_id": uuid,
        "created_by_id": uuid,
    },
}

update_template_email_files_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST create new email linked file",
    "type": "object",
    "title": "payload for POST /service/<uuid:service_id>/template",
    "properties": {
        "id": uuid,
        "filename": {"type": "string"},
        "link_text": {"type": "string"},
        "service": uuid,
        "retention_period": {"type": "integer"},
        "validate_users_email": {"type": "boolean"},
        "template_id": uuid,
        "template_version": {"type": "integer"},
        "archived_by_id": uuid,
    },
}

post_archive_template_email_files_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST schema for archiving letter_attachment",
    "type": "object",
    "properties": {
        "archived_by_id": uuid,
    },
    "required": ["archived_by_id"],
}
