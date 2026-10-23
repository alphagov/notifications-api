import itertools

from flask import current_app
from notifications_utils.recipients import allowed_to_send_to

from app.constants import (
    EMAIL_TYPE,
    KEY_TYPE_NORMAL,
    KEY_TYPE_TEST,
    MOBILE_TYPE,
)
from app.dao.services_dao import dao_fetch_service_by_id
from app.models import ServiceGuestList


def get_recipients_from_request(request_json, key, type):
    return [(type, recipient) for recipient in request_json.get(key)]


def get_guest_list_objects(service_id, request_json):
    return [
        ServiceGuestList.from_string(service_id, type, recipient)
        for type, recipient in (
            get_recipients_from_request(request_json, "phone_numbers", MOBILE_TYPE)
            + get_recipients_from_request(request_json, "email_addresses", EMAIL_TYPE)
        )
    ]


def service_allowed_to_send_to(recipient, service, key_type, allow_guest_list_recipients=True):
    if key_type == KEY_TYPE_TEST:
        return True

    if key_type == KEY_TYPE_NORMAL and not service.restricted:
        return True

    # Revert back to the ORM model here so we can get some things which
    # aren’t in the serialised model
    service = dao_fetch_service_by_id(service.id)

    allowed_recipients = itertools.chain(
        [user.email_address for user in service.users],
        [user.mobile_number for user in service.users],
        [member.recipient for member in service.guest_list if allow_guest_list_recipients],
        current_app.config["SIMULATED_EMAIL_ADDRESSES"],
        current_app.config["SIMULATED_SMS_NUMBERS"],
    )

    return allowed_to_send_to(recipient, allowed_recipients)
