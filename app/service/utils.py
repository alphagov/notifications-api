from app.models import (
    ServiceWhitelist,
    MOBILE_TYPE, EMAIL_TYPE)


def get_recipients_from_request(request_json, key, type):
    return [(type, recipient) for recipient in request_json.get(key)]


def get_whitelist_objects(service_id, request_json):
    return [
        ServiceWhitelist.from_string(service_id, type, recipient)
        for type, recipient in (
            get_recipients_from_request(request_json, 'phone_numbers', MOBILE_TYPE) +
            get_recipients_from_request(request_json, 'email_addresses', EMAIL_TYPE)
        )
    ]
