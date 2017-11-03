post_verify_code_schema = {
    '$schema': 'http://json-schema.org/draft-04/schema#',
    'description': 'POST schema for verifying a 2fa code',
    'type': 'object',
    'properties': {
        'code': {'type': 'string'},
        'code_type': {'type': 'string'},
    },
    'required': ['code', 'code_type']
}


post_send_user_email_code_schema = {
    '$schema': 'http://json-schema.org/draft-04/schema#',
    'description': 'POST schema for generating a 2fa email',
    'type': 'object',
    'properties': {
        # doesn't need 'to' as we'll just grab user.email_address
        'next': {'type': ['string', 'null']},
    },
    'required': [],
    'additionalProperties': []
}


post_send_user_sms_code_schema = {
    '$schema': 'http://json-schema.org/draft-04/schema#',
    'description': 'POST schema for generating a 2fa email',
    'type': 'object',
    'properties': {
        'to': {'type': ['string', 'null']},
    },
    'required': [],
    'additionalProperties': []
}
