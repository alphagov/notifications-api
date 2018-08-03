add_service_data_retention_request = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "POST service data retention schema",
    "title": "Add service data retention for notification type api",
    "type": "object",
    "properties": {
        "days_of_retention": {"type": "integer"},
        "notification_type": {"enum": ["sms", "letter", "email"]},
    },
    "required": ["days_of_retention", "notification_type"]
}


update_service_data_retention_request = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "POST service data retention schema",
    "title": "Update service data retention for notification type api",
    "type": "object",
    "properties": {
        "days_of_retention": {"type": "integer"},
    },
    "required": ["days_of_retention"]
}
