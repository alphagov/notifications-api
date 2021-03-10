from app.models import BroadcastStatusType
from app.schema_validation.definitions import uuid

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
        'starts_at': {'type': 'string', 'format': 'datetime'},
        'finishes_at': {'type': 'string', 'format': 'datetime'},
        'areas': {"type": "array", "items": {"type": "string"}},
        'simple_polygons': {"type": "array", "items": {"type": "array"}},
        'content': {'type': 'string', 'minLength': 1, 'maxLength': 1395},
        'reference': {'type': 'string', 'minLength': 1, 'maxLength': 255},
    },
    'required': ['service_id', 'created_by'],
    'allOf': [
        {'oneOf': [
            {'required': ['template_id']},
            {'required': ['content']},
        ]},
        {'oneOf': [
            {'required': ['template_id']},
            {'required': ['reference']},
        ]},
    ],
    'additionalProperties': False
}

update_broadcast_message_schema = {
    '$schema': 'http://json-schema.org/draft-04/schema#',
    'description': 'POST update broadcast_message schema',
    'type': 'object',
    'title': 'Update broadcast_message',
    'properties': {
        'personalisation': {'type': 'object'},
        'starts_at': {'type': 'string', 'format': 'datetime'},
        'finishes_at': {'type': 'string', 'format': 'datetime'},
        'areas': {"type": "array", "items": {"type": "string"}},
        'simple_polygons': {"type": "array", "items": {"type": "array"}},
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
