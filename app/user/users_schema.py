post_verify_code_schema = {
    '$schema': 'http://json-schema.org/draft-04/schema#',
    'description': 'POST schema for verifying a 2fa code',
    'type': 'object',
    'properties': {
        'code': {'type': 'string'},
        'code_type': {'type': 'string'},
    },
    'required': ['code', 'code_type'],
    'additionalProperties': False
}


post_send_user_email_code_schema = {
    '$schema': 'http://json-schema.org/draft-04/schema#',
    'description': (
        'POST schema for generating a 2fa email - "to" is required for legacy purposes. '
        '"next" is an optional url to redirect to on sign in'
    ),
    'type': 'object',
    'properties': {
        # does not need 'to' as we'll just grab user.email_address. but lets keep it
        # as allowed to keep admin code cleaner, but only as null to prevent confusion
        'to': {'type': 'null'},
        'email_auth_link_host': {'type': ['string', 'null']},
        'next': {'type': ['string', 'null']},
    },
    'required': [],
    'additionalProperties': False
}


post_send_user_sms_code_schema = {
    '$schema': 'http://json-schema.org/draft-04/schema#',
    'description': 'POST schema for generating a 2fa sms',
    'type': 'object',
    'properties': {
        'to': {'type': ['string', 'null']},
    },
    'required': [],
    'additionalProperties': False
}


post_set_permissions_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST schema for setting user permissions",
    "type": "object",
    "properties": {
        "permissions": {"type": "array", "items": {"type": "object"}},
        "folder_permissions": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["permissions"],
    "additionalProperties": False
}
