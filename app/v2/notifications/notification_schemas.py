from app.schema_validation.definitions import (uuid, personalisation)

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
    "required": ["body"]
}

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

post_sms_response = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "POST sms notification response schema",
    "type": "object",
    "title": "response v2/notifications/sms",
    "properties": {
        "id": uuid,
        "reference": {"type": "string"},
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
    "required": ["body"]
}

post_email_response = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "POST sms notification response schema",
    "type": "object",
    "title": "response v2/notifications/email",
    "properties": {
        "id": uuid,
        "reference": {"type": "string"},
        "content": email_content,
        "uri": {"type": "string"},
        "template": template
    },
    "required": ["id", "content", "uri", "template"]
}


def create_post_sms_response_from_notification(notification, body, from_number, url_root):
    return {"id": notification.id,
            "reference": None,  # not yet implemented
            "content": {'body': body,
                        'from_number': from_number},
            "uri": "{}/v2/notifications/{}".format(url_root, str(notification.id)),
            "template": __create_template_from_notification(notification=notification, url_root=url_root)
            }


def create_post_email_response_from_notification(notification, content, subject, email_from, url_root):
    return {
        "id": notification.id,
        "reference": notification.reference,
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
