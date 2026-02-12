from app.schema_validation.definitions import uuid

post_create_template_email_files_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST create new email linked file",
    "type": "object",
    "title": "payload for POST payload for POST /service/<uuid:service_id>/template/<uuid:template_id>/template_email_files/",  # noqa: E501
    "properties": {
        "id": uuid,
        "filename": {"type": "string"},
        "link_text": {"type": "string"},
        "service": uuid,
        "retention_period": {"type": "integer", "format": "send_file_via_ui_retention_period"},
        "validate_users_email": {"type": "boolean"},
        "created_by_id": uuid,
    },
}

update_template_email_files_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST create new email linked file",
    "type": "object",
    "title": "payload for POST /service/<uuid:service_id>/template/<uuid:template_id>/template_email_files/<uuid:template_email_file_id>",  # noqa: E501
    "properties": {
        "id": uuid,
        "filename": {"type": "string"},
        "link_text": {"type": "string"},
        "service": uuid,
        "retention_period": {"type": "integer", "format": "send_file_via_ui_retention_period"},
        "validate_users_email": {"type": "boolean"},
        "template_version": {"type": "integer"},
        "archived_by_id": uuid,
    },
}

post_archive_template_email_files_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST schema for archiving template_emails_file",
    "type": "object",
    "properties": {
        "archived_by_id": uuid,
    },
    "required": ["archived_by_id"],
}
