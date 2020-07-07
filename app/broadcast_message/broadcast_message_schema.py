from app.schema_validation.definitions import uuid
from app.models import BroadcastStatusType

create_broadcast_message_schema = {
    '$schema': 'http://json-schema.org/draft-04/schema#',
    'description': 'POST create broadcast_message schema',
    'type': 'object',
    'title': 'Create broadcast_message',
    'properties': {
        'template_id': uuid,
        'service_id': uuid,
        'created_by': uuid,
        'personalisation': {'type': 'object'},
        'starts_at': {'type': 'string', 'format': 'date-time'},
        'finishes_at': {'type': 'string', 'format': 'date-time'},
        'areas': {"type": "array", "items": {"type": "string"}},
    },
    'required': ['template_id', 'service_id', 'created_by'],
    'additionalProperties': False
}

update_broadcast_message_schema = {
    '$schema': 'http://json-schema.org/draft-04/schema#',
    'description': 'POST update broadcast_message schema',
    'type': 'object',
    'title': 'Update broadcast_message',
    'properties': {
        'personalisation': {'type': 'object'},
        'starts_at': {'type': 'string', 'format': 'date-time'},
        'finishes_at': {'type': 'string', 'format': 'date-time'},
        'areas': {"type": "array", "items": {"type": "string"}},
    },
    'required': [],
    'additionalProperties': False
}

update_broadcast_message_status_schema = {
    '$schema': 'http://json-schema.org/draft-04/schema#',
    'description': 'POST update broadcast_message status schema',
    'type': 'object',
    'title': 'Update broadcast_message',
    'properties': {
        'status': {'type': 'string', 'enum': BroadcastStatusType.STATUSES},
        'created_by': uuid,
    },
    'required': ['status', 'created_by'],
    'additionalProperties': False
}
