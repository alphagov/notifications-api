from app.constants import (
    NOTIFICATION_STATUS_LETTER_ACCEPTED,
    NOTIFICATION_STATUS_LETTER_RECEIVED,
    NOTIFICATION_STATUS_TYPES,
    NOTIFICATION_TYPES,
)
from app.schema_validation.definitions import https_url, personalisation, uuid

template = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "template schema",
    "type": "object",
    "title": "notification content",
    "properties": {"id": uuid, "version": {"type": "integer"}, "uri": {"type": "string", "format": "uri"}},
    "required": ["id", "version", "uri"],
}

notification_by_id = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "GET notification response schema",
    "type": "object",
    "title": "response v2/notification",
    "properties": {"notification_id": uuid},
    "required": ["notification_id"],
}


get_notification_response = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "GET notification response schema",
    "type": "object",
    "title": "response v2/notification",
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
        "body": {"type": "string"},
        "subject": {"type": ["string", "null"]},
        "created_at": {"type": "string"},
        "sent_at": {"type": ["string", "null"]},
        "completed_at": {"type": ["string", "null"]},
        "scheduled_for": {"type": ["string", "null"]},
    },
    "required": [
        # technically, all keys are required since we always have all of them
        "id",
        "reference",
        "email_address",
        "phone_number",
        "line_1",
        "line_2",
        "line_3",
        "line_4",
        "line_5",
        "line_6",
        "postcode",
        "type",
        "status",
        "template",
        "body",
        "created_at",
        "sent_at",
        "completed_at",
    ],
}

get_notifications_request = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "schema for query parameters allowed when getting list of notifications",
    "type": "object",
    "properties": {
        "reference": {"type": "string"},
        "status": {
            "type": "array",
            "items": {
                "enum": NOTIFICATION_STATUS_TYPES
                + [NOTIFICATION_STATUS_LETTER_ACCEPTED, NOTIFICATION_STATUS_LETTER_RECEIVED]
            },
        },
        "template_type": {"type": "array", "items": {"enum": NOTIFICATION_TYPES}},
        "include_jobs": {"enum": ["true", "True"]},
        "older_than": uuid,
    },
    "additionalProperties": False,
}

get_notifications_response = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "GET list of notifications response schema",
    "type": "object",
    "properties": {
        "notifications": {"type": "array", "items": {"type": "object", "$ref": "#/definitions/notification"}},
        "links": {
            "type": "object",
            "properties": {"current": {"type": "string"}, "next": {"type": "string"}},
            "additionalProperties": False,
            "required": ["current"],
        },
    },
    "additionalProperties": False,
    "required": ["notifications", "links"],
    "definitions": {"notification": get_notification_response},
}

send_a_file_validation = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "file": {
            "type": "string",
            "required": True,
        },
        "is_csv": {
            "format": "send_a_file_is_csv",
        },
        "confirm_email_before_download": {
            "format": "send_a_file_confirm_email_before_download",
            "required": False,
        },
        "retention_period": {
            "format": "send_a_file_retention_period",
            "required": False,
        },
        "filename": {
            "format": "send_a_file_filename",
        },
    },
    "allOf": [
        {
            "anyOf": [
                {"not": {"required": ["is_csv"]}},
                {"not": {"required": ["filename"]}},
            ],
            "validationMessage": "Do not set a value for `is_csv` if `filename` is set.",
        }
    ],
}

post_sms_request = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST sms notification schema",
    "type": "object",
    "title": "POST v2/notifications/sms",
    "properties": {
        "reference": {"type": "string", "maxLength": 1_000},
        "phone_number": {"type": "string", "format": "phone_number"},
        "template_id": uuid,
        "personalisation": personalisation,
        "scheduled_for": {"type": ["string", "null"], "format": "datetime_within_next_day"},
        "sms_sender_id": uuid,
    },
    "required": ["phone_number", "template_id"],
    "additionalProperties": False,
}

sms_content = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "content schema for SMS notification response schema",
    "type": "object",
    "title": "notification content",
    "properties": {"body": {"type": "string"}, "from_number": {"type": "string"}},
    "required": ["body", "from_number"],
}

post_sms_response = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST sms notification response schema",
    "type": "object",
    "title": "response v2/notifications/sms",
    "properties": {
        "id": uuid,
        "reference": {"type": ["string", "null"]},
        "content": sms_content,
        "uri": {"type": "string", "format": "uri"},
        "template": template,
        "scheduled_for": {"type": ["string", "null"]},
    },
    "required": ["id", "content", "uri", "template"],
}


post_email_request = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST email notification schema",
    "type": "object",
    "title": "POST v2/notifications/email",
    "properties": {
        "reference": {"type": "string", "maxLength": 1_000},
        "email_address": {"type": "string", "format": "email_address"},
        "template_id": uuid,
        "personalisation": personalisation,
        "scheduled_for": {"type": ["string", "null"], "format": "datetime_within_next_day"},
        "email_reply_to_id": uuid,
        "unsubscribe_link": https_url,
    },
    "required": ["email_address", "template_id"],
    "additionalProperties": False,
}

email_content = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "Email content for POST email notification",
    "type": "object",
    "title": "notification email content",
    "properties": {
        "from_email": {"type": "string", "format": "email_address"},
        "body": {"type": "string"},
        "subject": {"type": "string"},
    },
    "required": ["body", "from_email", "subject"],
}

post_email_response = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST email notification response schema",
    "type": "object",
    "title": "response v2/notifications/email",
    "properties": {
        "id": uuid,
        "reference": {"type": ["string", "null"]},
        "content": email_content,
        "uri": {"type": "string", "format": "uri"},
        "template": template,
        "scheduled_for": {"type": ["string", "null"]},
    },
    "required": ["id", "content", "uri", "template"],
}

post_letter_request = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST letter notification schema",
    "type": "object",
    "title": "POST v2/notifications/letter",
    "properties": {
        "reference": {"type": "string", "maxLength": 1_000},
        "template_id": uuid,
        "personalisation": personalisation,
    },
    "required": ["template_id", "personalisation"],
    "additionalProperties": False,
}

post_precompiled_letter_request = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST precompiled letter notification schema",
    "type": "object",
    "title": "POST v2/notifications/letter",
    "properties": {
        "reference": {"type": "string"},
        "content": {"type": "string"},
        "postage": {"type": "string", "format": "postage"},
    },
    "required": ["reference", "content"],
    "additionalProperties": False,
}

letter_content = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "Letter content for POST letter notification",
    "type": "object",
    "title": "notification letter content",
    "properties": {"body": {"type": "string"}, "subject": {"type": "string"}},
    "required": ["body", "subject"],
}

post_letter_response = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST sms notification response schema",
    "type": "object",
    "title": "response v2/notifications/letter",
    "properties": {
        "id": uuid,
        "reference": {"type": ["string", "null"]},
        "content": letter_content,
        "uri": {"type": "string", "format": "uri"},
        "template": template,
        # letters cannot be scheduled
        "scheduled_for": {"type": "null"},
    },
    "required": ["id", "content", "uri", "template"],
}
