from flask import jsonify, current_app, Blueprint
from apispec import APISpec


spec = Blueprint('spec', __name__)


api_spec = APISpec(
    title='GOV.UK Notify',
    version='0.0.0'
)

api_spec.definition('NotificationWithTemplateSchema', properties={
    "content_char_count": {
        "format": "int32",
        "type": "integer"
    },
    "created_at": {
        "format": "date-time",
        "type": "string"
    },
    "id": {
        "format": "uuid",
        "type": "string"
    },
    "job": {
        "properties": {
            "id": {
                "format": "uuid",
                "type": "string"
            },
            "original_file_name": {
                "type": "string"
            }
        },
        "required": [
            "id",
            "original_file_name"
        ],
        "type": "object"
    },
    "job_row_number": {
        "format": "int32",
        "type": "integer"
    },
    "reference": {
        "type": "string"
    },
    "sent_at": {
        "format": "date-time",
        "type": "string"
    },
    "sent_by": {
        "type": "string"
    },
    "service": {
        "type": "string"
    },
    "status": {
        "enum": [
            "delivered",
            "sending",
            "technical-failure",
            "temporary-failure",
            "permanent-failure",
            "pending",
            "failed"
        ],
        "type": "string"
    },
    "template": {
        "properties": {
            "id": {
                "format": "uuid",
                "type": "string"
            },
            "name": {
                "type": "string"
            },
            "template_type": {
                "enum": [
                    "sms",
                    "email",
                    "letter"
                ],
                "type": "string"
            }
        },
        "required": [
            "template_type",
            "name"
        ],
        "type": "object"
    },
    "template_version": {
        "format": "int32",
        "type": "integer"
    },
    "to": {
        "type": "string"
    },
    "updated_at": {
        "format": "date-time",
        "type": "string"
    }
})
api_spec.definition('NotificationSchema', properties={
    "notification": {
        "$ref": "#/definitions/NotificationWithTemplateSchema"
    }
})
api_spec.definition('NotificationsSchema', properties={
    "notifications": {
        "type": "array",
        "items": {
            "$ref": "#/definitions/NotificationWithTemplateSchema"
        }
    }
})
api_spec.definition('NotificationSentSchema', properties={
    "body": {
        "description": "The content of the message",
        "type": "string"
    },
    "notification": {
        "properties": {
            "id": {
                "type": "string"
            }
        },
        "type": "object"
    },
    "subject": {
        "description": "The subject of the email (present for email notifications only)",
        "type": "string"
    },
    "template_version": {
        "description": "The version number of the template that was used",
        "type": "integer"
    }
})
api_spec.definition('Error', properties={
    'result': {
        'type': 'string',
        'description': 'will say ‘error’'
    },
    'message': {
        'type': 'string',
        'description': 'description of the error'
    }
})
api_spec.add_path(path="/notifications", operations={
    "get": {
        "parameters": [
            {
                "description": "page number",
                "in": "query",
                "name": "page",
                "type": "integer"
            },
            {
                "default": 50,
                "description": "number of notifications per page",
                "in": "query",
                "name": "page_size",
                "type": "integer"
            },
            {
                "default": 7,
                "description": "number of days",
                "in": "query",
                "name": "limit_days",
                "type": "integer"
            },
            {
                "description": "sms or email",
                "enum": [
                    "sms",
                    "email"
                ],
                "in": "query",
                "name": "template_type",
                "type": "string"
            },
            {
                "description": "sms or email",
                "in": "query",
                "name": "status",
                "type": "string"
            }
        ],
        "responses": {
            "200": {
                "description": "Notifications found",
                "schema": {
                    "$ref": "#/definitions/NotificationsSchema"
                }
            },
            "400": {
                "description": "Bad request",
                "schema": {
                    "$ref": "#/definitions/Error"
                }
            },
            "401": {
                "description": "Authorisation header is missing",
                "schema": {
                    "$ref": "#/definitions/Error"
                }
            },
            "403": {
                "description": "Invalid or expired token",
                "schema": {
                    "$ref": "#/definitions/Error"
                }
            },
            "404": {
                "description": "No notifications found"
            }
        }
    }
})
api_spec.add_path(path="/notification/{notification_id_or_type}", operations={
    "get": {
        "parameters": [
            {
                "description": "16 character UUID",
                "in": "path",
                "name": "notification_id_or_type",
                "required": True,
                "type": "string"
            }
        ],
        "responses": {
            "200": {
                "description": "Found",
                "schema": {
                    "$ref": "#/definitions/NotificationSchema"
                }
            },
            "401": {
                "description": "Authorisation header is missing",
                "schema": {
                    "$ref": "#/definitions/Error"
                }
            },
            "403": {
                "description": "Invalid or expired token",
                "schema": {
                    "$ref": "#/definitions/Error"
                }
            },
            "404": {
                "description": "Not found"
            }
        }
    },
    "post": {
        "description": "Send a single email or text message",
        "parameters": [
            {
                "description": "email or sms",
                "in": "path",
                "name": "notification_id_or_type",
                "pattern": "[email|sms]",
                "required": True,
                "type": "string"
            },
            {
                "description": "the recipient's phone number or email address",
                "in": "formData",
                "name": "to",
                "required": True,
                "type": "string"
            },
            {
                "description": "the ID of the template to use",
                "in": "formData",
                "name": "template",
                "required": True,
                "type": "string"
            },
            {
                "description": "specifies the placeholders and values in your templates",
                "in": "formData",
                "name": "personalisation",
                "type": "string"
            }
        ],
        "responses": {
            "200": {
                "description": "Notification sent",
                "schema": {
                    "$ref": "#/definitions/NotificationSentSchema"
                }
            },
            "400": {
                "description": "Bad request",
                "schema": {
                    "$ref": "#/definitions/Error"
                }
            },
            "401": {
                "description": "Authorisation header is missing",
                "schema": {
                    "$ref": "#/definitions/Error"
                }
            },
            "403": {
                "description": "Invalid or expired token",
                "schema": {
                    "$ref": "#/definitions/Error"
                }
            },
            "429": {
                "description": "You have reached the maximum number of messages you can send per day",
                "schema": {
                    "$ref": "#/definitions/Error"
                }
            }
        }
    }
})


@spec.route('')
def get_spec():
    return jsonify(api_spec.to_dict())
