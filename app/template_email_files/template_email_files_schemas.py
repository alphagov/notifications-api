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
        "retention_period": {"type": "integer"},
        "validate_users_email": {"type": "boolean"},
        "created_by_id": uuid,
    },
    # all of these are always sent by the create endpoint in admin app, so we should always have data for them
    "required": ["id", "filename", "created_by_id", "retention_period", "validate_users_email"],
}

post_update_template_email_files_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST update email linked file",
    "type": "object",
    "title": "payload for POST /service/<uuid:service_id>/template/<uuid:template_id>/template_email_files/<uuid:template_email_file_id>",  # noqa: E501
    "properties": {
        "id": uuid,
        "filename": {"type": "string"},
        "link_text": {"type": "string"},
        "service": uuid,
        "template": uuid,
        "retention_period": {"type": "integer"},
        "validate_users_email": {"type": "boolean"},
        "template_version": {"type": "integer"},
        "archived_by_id": uuid,
        "pending": {"type": "boolean"},
    },
    # all of these are always sent by the update endpoint in admin app, so we should always have data for them
    "required": ["link_text", "retention_period", "validate_users_email", "pending"],
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
