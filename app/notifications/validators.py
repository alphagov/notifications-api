from math import ceil

from flask import current_app
from gds_metrics.metrics import Histogram
from notifications_utils import SMS_CHAR_COUNT_LIMIT
from notifications_utils.clients.redis import daily_limit_cache_key
from notifications_utils.recipient_validation.email_address import validate_and_format_email_address
from notifications_utils.recipient_validation.errors import InvalidPhoneError
from notifications_utils.recipient_validation.phone_number import PhoneNumber
from notifications_utils.recipient_validation.postal_address import PostalAddress
from sqlalchemy.orm.exc import NoResultFound

from app import redis_store
from app.constants import (
    EMAIL_TYPE,
    INTERNATIONAL_LETTERS,
    INTERNATIONAL_SMS_TYPE,
    KEY_TYPE_TEAM,
    KEY_TYPE_TEST,
    LETTER_TYPE,
    SECONDS_IN_1_MINUTE,
    SMS_TO_UK_LANDLINES,
    SMS_TYPE,
    TOKEN_BUCKET_MAX,
    TOKEN_BUCKET_MIN,
)
from app.dao.service_email_reply_to_dao import dao_get_reply_to_by_id
from app.dao.service_letter_contact_dao import dao_get_letter_contact_by_id
from app.dao.service_sms_sender_dao import dao_get_service_sms_senders_by_id
from app.notifications.process_notifications import (
    create_content_for_notification,
)
from app.serialised_models import SerialisedTemplate
from app.service.utils import service_allowed_to_send_to
from app.utils import get_public_notify_type_text
from app.v2.errors import (
    BadRequestError,
    RateLimitError,
    TooManyRequestsError,
    ValidationError,
)

REDIS_EXCEEDED_RATE_LIMIT_DURATION_SECONDS = Histogram(
    "redis_exceeded_rate_limit_duration_seconds",
    "Time taken to check rate limit",
    ["algorithm"],
)


def check_service_over_api_rate_limit(service, key_type):
    if not current_app.config["API_RATE_LIMIT_ENABLED"]:
        return
    if not current_app.config["REDIS_ENABLED"]:
        return
    if token_bucket_rate_limit_exceeded(service, key_type):
        current_app.logger.info("service %s has been rate limited for token bucket", service.id)
        raise RateLimitError(service.rate_limit, SECONDS_IN_1_MINUTE, key_type)


def token_bucket_rate_limit_exceeded(service, key_type):
    with REDIS_EXCEEDED_RATE_LIMIT_DURATION_SECONDS.labels(algorithm="token_bucket").time():
        remaining = redis_store.get_remaining_bucket_tokens(
            key=f"{service.id}-tokens-{key_type}",
            replenish_per_sec=service.rate_limit / SECONDS_IN_1_MINUTE,
            bucket_max=min(ceil(service.rate_limit / 3) + 1, TOKEN_BUCKET_MAX),
            bucket_min=TOKEN_BUCKET_MIN,
        )

        if remaining is None:
            # we have troubles reaching redis and should allow this
            return False

        return remaining < 1


def get_daily_rate_limit_value(service, key_type, notification_type):
    if key_type == KEY_TYPE_TEST and service.restricted:
        rate_limits = current_app.config["DEFAULT_LIVE_SERVICE_RATE_LIMITS"]
        rate_limits["international_sms"] = current_app.config["DEFAULT_SERVICE_INTERNATIONAL_SMS_LIMIT"]
    else:
        rate_limits = {
            EMAIL_TYPE: service.email_message_limit,
            SMS_TYPE: service.sms_message_limit,
            INTERNATIONAL_SMS_TYPE: service.international_sms_message_limit,
            LETTER_TYPE: service.letter_message_limit,
        }

    return rate_limits[notification_type]


def check_service_over_daily_message_limit(service, key_type, notification_type, num_notifications=1):
    if not current_app.config["REDIS_ENABLED"]:
        return

    limit_name = notification_type
    limit_value = get_daily_rate_limit_value(service, key_type, notification_type)

    cache_key = daily_limit_cache_key(service.id, notification_type=notification_type)
    if (service_stats := redis_store.get(cache_key)) is None:
        # first message of the day, set the cache to 0 and the expiry to 24 hours
        redis_store.set(cache_key, 0, ex=86400)

        service_stats = 0

    if int(service_stats) + num_notifications > limit_value:
        extra = {
            "service_id": service.id,
            "sent_count": int(service_stats),
            "notification_type": limit_name,
            "limit": limit_value,
        }
        current_app.logger.info(
            "Service %(service_id)s has been rate limited for %(sent_count)s daily use "
            "sent %(notification_type)s limit %(limit)s",
            extra,
            extra=extra,
        )
        raise TooManyRequestsError(limit_name, limit_value)


def check_rate_limiting(service, api_key, notification_type):
    check_service_over_api_rate_limit(service, api_key.key_type)
    check_service_over_daily_message_limit(service, api_key.key_type, notification_type=notification_type)


def check_template_is_for_notification_type(notification_type, template_type):
    if notification_type != template_type:
        message = f"{template_type} template is not suitable for {notification_type} notification"
        raise BadRequestError(fields=[{"template": message}], message=message)


def check_template_is_active(template):
    if template.archived:
        raise BadRequestError(fields=[{"template": "Template has been deleted"}], message="Template has been deleted")


def service_can_send_to_recipient(send_to, key_type, service, allow_guest_list_recipients=True):
    if not service_allowed_to_send_to(send_to, service, key_type, allow_guest_list_recipients):
        if key_type == KEY_TYPE_TEAM:
            message = "Can’t send to this recipient using a team-only API key"
        else:
            message = (
                "Can’t send to this recipient when service is in trial mode "
                "– see https://www.notifications.service.gov.uk/trial-mode"
            )
        raise BadRequestError(message=message)


def check_service_has_permission(service, permission):
    if not service.has_permission(permission):
        raise BadRequestError(
            message=f"Service is not allowed to send {get_public_notify_type_text(permission, plural=True)}"
        )


def check_if_service_can_send_files_by_email(service_contact_link, service_id):
    if not service_contact_link:
        raise BadRequestError(
            message=f"Send files by email has not been set up - add contact details for your service at "
            f"{current_app.config['ADMIN_BASE_URL']}/services/{service_id}/service-settings/send-files-by-email"
        )


def validate_and_format_recipient(
    send_to, key_type, service, notification_type, allow_guest_list_recipients=True, check_intl_sms_limit=True
):
    if send_to is None:
        raise BadRequestError(message="Recipient can't be empty")

    service_can_send_to_recipient(send_to, key_type, service, allow_guest_list_recipients)

    if notification_type == SMS_TYPE:
        return validate_and_return_extended_phone_number_info(
            service, send_to, key_type, check_intl_sms_limit=check_intl_sms_limit
        )

    elif notification_type == EMAIL_TYPE:
        return validate_and_format_email_address(email_address=send_to)


def validate_and_return_extended_phone_number_info(service, send_to, key_type, check_intl_sms_limit):
    try:
        phone_number = PhoneNumber(send_to)
        phone_number.validate(
            allow_international_number=service.has_permission(INTERNATIONAL_SMS_TYPE),
            allow_uk_landline=service.has_permission(SMS_TO_UK_LANDLINES),
        )

        recipient_data = _get_extended_phone_number_info(phone_number, send_to)

        if check_intl_sms_limit and not phone_number.is_uk_phone_number():
            check_service_over_daily_message_limit(service, key_type, notification_type=INTERNATIONAL_SMS_TYPE)

        return recipient_data

    except InvalidPhoneError as e:
        # only show "Not a UK mobile" error when a service tries to send to landline and is not allowed
        # in all other cases show "Cannot send to international mobile numbers"
        if e.code == InvalidPhoneError.Codes.NOT_A_UK_MOBILE and is_international_number(phone_number):
            raise BadRequestError(message="Cannot send to international mobile numbers") from e
        else:
            raise


def _get_extended_phone_number_info(phone_number, send_to):
    formatted_recipient = phone_number.get_normalised_format()
    recipient_info = phone_number.get_international_phone_info()

    return {
        "unformatted_recipient": send_to,
        "normalised_to": formatted_recipient,
        "international": recipient_info.international,
        "phone_prefix": recipient_info.country_prefix,
        "rate_multiplier": recipient_info.rate_multiplier,
    }


def is_international_number(phone_number):
    international_phone_info = phone_number.get_international_phone_info()

    return international_phone_info.international and not international_phone_info.crown_dependency


def check_is_message_too_long(template_with_content):
    if template_with_content.is_message_too_long():
        message = "Your message is too long. "
        if template_with_content.template_type == SMS_TYPE:
            message += (
                f"Text messages cannot be longer than {SMS_CHAR_COUNT_LIMIT} characters. "
                f"Your message is {template_with_content.content_count_without_prefix} characters long."
            )
        elif template_with_content.template_type == EMAIL_TYPE:
            message += (
                f"Emails cannot be longer than 2000000 bytes. "
                f"Your message is {template_with_content.content_size_in_bytes} bytes."
            )
        raise BadRequestError(message=message)


def check_notification_content_is_not_empty(template_with_content):
    if template_with_content.is_message_empty():
        message = "Your message is empty."
        raise BadRequestError(message=message)


def validate_template(template_id, personalisation, service, notification_type, check_char_count=True, recipient=None):
    try:
        template = SerialisedTemplate.from_id_and_service_id(template_id, service.id)
    except NoResultFound as e:
        message = "Template not found"
        raise BadRequestError(message=message, fields=[{"template": message}]) from e

    check_template_is_for_notification_type(notification_type, template.template_type)
    check_template_is_active(template)

    template_with_content = create_content_for_notification(template, personalisation, recipient)

    check_notification_content_is_not_empty(template_with_content)

    # validating the template in post_notifications happens before the file is uploaded for doc download,
    # which means the length of the message can be exceeded because it's including the file.
    # The document download feature is only available through the api.
    if check_char_count:
        check_is_message_too_long(template_with_content)

    check_template_can_contain_documents(notification_type, personalisation)

    return template, template_with_content


def check_service_email_reply_to_id(service_id, reply_to_id, notification_type):
    if reply_to_id:
        try:
            return dao_get_reply_to_by_id(reply_to_id=reply_to_id, service_id=service_id).email_address
        except NoResultFound as e:
            message = f"email_reply_to_id {reply_to_id} does not exist in database for service id {service_id}"
            raise BadRequestError(message=message) from e


def check_service_sms_sender_id(service_id, sms_sender_id, notification_type):
    if sms_sender_id:
        try:
            return dao_get_service_sms_senders_by_id(service_id, sms_sender_id).sms_sender
        except NoResultFound as e:
            message = f"sms_sender_id {sms_sender_id} does not exist in database for service id {service_id}"
            raise BadRequestError(message=message) from e


def check_service_letter_contact_id(service_id, letter_contact_id, notification_type):
    if letter_contact_id:
        try:
            return dao_get_letter_contact_by_id(service_id, letter_contact_id).contact_block
        except NoResultFound as e:
            message = f"letter_contact_id {letter_contact_id} does not exist in database for service id {service_id}"
            raise BadRequestError(message=message) from e


def validate_address(service, letter_data):
    address = PostalAddress.from_personalisation(
        letter_data,
        allow_international_letters=(INTERNATIONAL_LETTERS in str(service.permissions)),
    )
    if not address.has_enough_lines:
        raise ValidationError(message=f"Address must be at least {PostalAddress.MIN_LINES} lines")
    if address.has_too_many_lines:
        raise ValidationError(message=f"Address must be no more than {PostalAddress.MAX_LINES} lines")
    if address.has_invalid_country_for_bfpo_address:
        raise ValidationError(message="The last line of a BFPO address must not be a country.")
    if not address.has_valid_last_line:
        if address.allow_international_letters:
            raise ValidationError(message="Last line of address must be a real UK postcode or another country")
        raise ValidationError(message="Must be a real UK postcode")
    if address.has_invalid_characters:
        raise ValidationError(
            message="Address lines must not start with any of the following characters: @ ( ) = [ ] ” \\ / , < >"
        )
    if address.has_no_fixed_abode_address:
        raise ValidationError(message="Must be a real address")
    if address.international:
        return address.postage
    else:
        return None


def check_template_can_contain_documents(template_type, personalisation):
    if template_type != EMAIL_TYPE and any(
        isinstance(v, dict) and "file" in v for v in (personalisation or {}).values()
    ):
        raise BadRequestError(message="Can only send a file by email")
