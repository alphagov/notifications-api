from app.models import NOTIFICATION_STATUS_TYPES, TEMPLATE_TYPES
from app.schema_validation.definitions import (uuid, personalisation)

# this may belong in a templates module
template = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "template schema",
    "type": "object",
    "title": "notification content",
    "properties": {
        "id": uuid,
        "version": {"type": "integer"},
        "uri": {"type": "string"}
    },
    "required": ["id", "version", "uri"]
}

get_notification_response = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "GET notification response schema",
    "type": "object",
    "title": "response v2/notification",
    "oneOf": [
        {"properties": {
            "email_address": {"type": "string", "format": "email_address"},
            "type": {"enum": ["email"]},

            "phone_number": {"type": "null"},
            "line_1": {"type": "null"},
            "postcode": {"type": "null"}
        }},
        {"properties": {
            "phone_number": {"type": "string", "format": "phone_number"},
            "type": {"enum": ["sms"]},

            "email_address": {"type": "null"},
            "line_1": {"type": "null"},
            "postcode": {"type": "null"}
        }},
        {"properties": {
            "line_1": {"type": "string", "minLength": 1},
            "postcode": {"type": "string", "minLength": 1},
            "type": {"enum": ["letter"]},

            "email_address": {"type": "null"},
            "phone_number": {"type": "null"}
        }}
    ],
    "properties": {
        "id": uuid,
        "reference": {"type": ["string", "null"]},
        "email_address": {"type": ["string", "null"]},
        "phone_number": {"type": ["string", "null"]},
        "line_1": {"type": ["string", "null"]},
        "line_2": {"type": ["string", "null"]},
        "line_3": {"type": ["string", "null"]},
        "line_4": {"type": ["string", "null"]},
        "line_5": {"type": ["string", "null"]},
        "line_6": {"type": ["string", "null"]},
        "postcode": {"type": ["string", "null"]},
        "type": {"enum": ["sms", "letter", "email"]},
        "status": {"type": "string"},
        "template": template,
        "created_at": {"type": "string"},
        "sent_at": {"type": ["string", "null"]},
        "completed_at": {"type": ["string", "null"]}
    },
    "required": [
        # technically, all keys are required since we always have all of them
        "id", "reference", "email_address", "phone_number",
        "line_1", "line_2", "line_3", "line_4", "line_5", "line_6", "postcode",
        "type", "status", "template", "created_at", "sent_at", "completed_at"
    ]
}

get_notifications_request = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "schema for query parameters allowed when getting list of notifications",
    "type": "object",
    "properties": {
        "reference": {"type": "string"},
        "status": {
            "type": "array",
            "items": {
                "enum": NOTIFICATION_STATUS_TYPES
            }
        },
        "template_type": {
            "type": "array",
            "items": {
                "enum": TEMPLATE_TYPES
            }
        },
        "older_than": uuid
    },
    "additionalProperties": False,
}

get_notifications_response = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "GET list of notifications response schema",
    "type": "object",
    "properties": {
        "notifications": {
            "type": "array",
            "items": {
                "type": "object",
                "ref": get_notification_response
            }
        },
        "links": {
            "type": "object",
            "properties": {
                "current": {
                    "type": "string"
                },
                "next": {
                    "type": "string"
                }
            },
            "additionalProperties": False,
            "required": ["current"]
        }
    },
    "additionalProperties": False,
    "required": ["notifications", "links"]
}

post_sms_request = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "POST sms notification schema",
    "type": "object",
    "title": "POST v2/notifications/sms",
    "properties": {
        "reference": {"type": "string"},
        "phone_number": {"type": "string", "format": "phone_number"},
        "template_id": uuid,
        "personalisation": personalisation
    },
    "required": ["phone_number", "template_id"]
}

sms_content = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "content schema for SMS notification response schema",
    "type": "object",
    "title": "notification content",
    "properties": {
        "body": {"type": "string"},
        "from_number": {"type": "string"}
    },
    "required": ["body", "from_number"]
}

post_sms_response = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "POST sms notification response schema",
    "type": "object",
    "title": "response v2/notifications/sms",
    "properties": {
        "id": uuid,
        "reference": {"type": ["string", "null"]},
        "content": sms_content,
        "uri": {"type": "string"},
        "template": template
    },
    "required": ["id", "content", "uri", "template"]
}


post_email_request = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "POST email notification schema",
    "type": "object",
    "title": "POST v2/notifications/email",
    "properties": {
        "reference": {"type": "string"},
        "email_address": {"type": "string", "format": "email_address"},
        "template_id": uuid,
        "personalisation": personalisation
    },
    "required": ["email_address", "template_id"]
}

email_content = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "Email content for POST email notification",
    "type": "object",
    "title": "notification email content",
    "properties": {
        "from_email": {"type": "string", "format": "email_address"},
        "body": {"type": "string"},
        "subject": {"type": "string"}
    },
    "required": ["body", "from_email", "subject"]
}

post_email_response = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "POST sms notification response schema",
    "type": "object",
    "title": "response v2/notifications/email",
    "properties": {
        "id": uuid,
        "reference": {"type": ["string", "null"]},
        "content": email_content,
        "uri": {"type": "string"},
        "template": template
    },
    "required": ["id", "content", "uri", "template"]
}


def create_post_sms_response_from_notification(notification, body, from_number, url_root):
    return {"id": notification.id,
            "reference": notification.client_reference,
            "content": {'body': body,
                        'from_number': from_number},
            "uri": "{}/v2/notifications/{}".format(url_root, str(notification.id)),
            "template": __create_template_from_notification(notification=notification, url_root=url_root)
            }


def create_post_email_response_from_notification(notification, content, subject, email_from, url_root):
    return {
        "id": notification.id,
        "reference": notification.client_reference,
        "content": {
            "from_email": email_from,
            "body": content,
            "subject": subject
        },
        "uri": "{}/v2/notifications/{}".format(url_root, str(notification.id)),
        "template": __create_template_from_notification(notification=notification, url_root=url_root)
    }


def __create_template_from_notification(notification, url_root):
    return {
        "id": notification.template_id,
        "version": notification.template_version,
        "uri": "{}/v2/templates/{}".format(url_root, str(notification.template_id))
    }
