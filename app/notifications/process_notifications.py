import uuid
from datetime import datetime

from flask import current_app
from gds_metrics import Histogram
from notifications_utils.clients import redis
from notifications_utils.recipient_validation.email_address import (
    format_email_address,
)
from notifications_utils.recipient_validation.errors import InvalidPhoneError
from notifications_utils.recipient_validation.phone_number import (
    PhoneNumber,
)
from notifications_utils.template import (
    LetterPrintTemplate,
    PlainTextEmailTemplate,
    SMSMessageTemplate,
)

from app import redis_store
from app.celery import provider_tasks
from app.celery.letters_pdf_tasks import get_pdf_for_templated_letter
from app.config import QueueNames
from app.constants import (
    EMAIL_TYPE,
    INTERNATIONAL_POSTAGE_TYPES,
    KEY_TYPE_TEST,
    LETTER_TYPE,
    NOTIFICATION_CREATED,
    NOTIFICATION_VALIDATION_FAILED,
    SMS_TO_UK_LANDLINES,
    SMS_TYPE,
)
from app.dao.notifications_dao import (
    dao_create_notification,
    dao_delete_notifications_by_id,
)
from app.models import Notification
from app.utils import parse_and_format_phone_number
from app.v2.errors import BadRequestError, QrCodeTooLongError

REDIS_GET_AND_INCR_DAILY_LIMIT_DURATION_SECONDS = Histogram(
    "redis_get_and_incr_daily_limit_duration_seconds",
    "Time taken to get and possibly incremement the daily limit cache key",
)


def create_content_for_notification(template, personalisation):
    if template.template_type == EMAIL_TYPE:
        template_object = PlainTextEmailTemplate(
            {
                "content": template.content,
                "subject": template.subject,
                "template_type": template.template_type,
            },
            personalisation,
        )
    if template.template_type == SMS_TYPE:
        template_object = SMSMessageTemplate(
            {
                "content": template.content,
                "template_type": template.template_type,
            },
            personalisation,
        )
    if template.template_type == LETTER_TYPE:
        template_object = LetterPrintTemplate(
            {
                "content": template.content,
                "subject": template.subject,
                "template_type": template.template_type,
            },
            personalisation,
            contact_block=template.reply_to_text,
        )

        if error := template_object.has_qr_code_with_too_much_data():
            raise QrCodeTooLongError(
                message="Cannot create a usable QR code - the link is too long",
                status_code=400,
                num_bytes=error.num_bytes,
                max_bytes=error.max_bytes,
                data=error.data,
            )

    check_placeholders(template_object)

    return template_object


def check_placeholders(template_object):
    if template_object.missing_data:
        message = "Missing personalisation: {}".format(", ".join(template_object.missing_data))
        raise BadRequestError(fields=[{"template": message}], message=message)


def persist_notification(
    *,
    template_id,
    template_version,
    recipient,
    service,
    personalisation,
    notification_type,
    api_key_id,
    key_type,
    created_at=None,
    job_id=None,
    job_row_number=None,
    reference=None,
    client_reference=None,
    notification_id=None,
    simulated=False,
    created_by_id=None,
    status=NOTIFICATION_CREATED,
    reply_to_text=None,
    unsubscribe_link=None,
    template_has_unsubscribe_link=False,
    billable_units=None,
    postage=None,
    document_download_count=None,
    updated_at=None,
):
    notification_created_at = created_at or datetime.utcnow()
    if not notification_id:
        notification_id = uuid.uuid4()

    notification = Notification(
        id=notification_id,
        template_id=template_id,
        template_version=template_version,
        to=recipient,
        service_id=service.id,
        personalisation=personalisation,
        notification_type=notification_type,
        api_key_id=api_key_id,
        key_type=key_type,
        created_at=notification_created_at,
        job_id=job_id,
        job_row_number=job_row_number,
        client_reference=client_reference,
        reference=reference,
        created_by_id=created_by_id,
        status=status,
        reply_to_text=reply_to_text,
        unsubscribe_link=unsubscribe_link,
        billable_units=billable_units,
        document_download_count=document_download_count,
        updated_at=updated_at,
    )
    if notification_type == SMS_TYPE:
        try:
            phonenumber = PhoneNumber(recipient)
            phonenumber.validate(
                allow_international_number=True, allow_uk_landline=service.has_permission(SMS_TO_UK_LANDLINES)
            )
            formatted_recipient = phonenumber.get_normalised_format()
            recipient_info = phonenumber.get_international_phone_info()
            notification.normalised_to = formatted_recipient
            notification.international = recipient_info.international
            notification.phone_prefix = recipient_info.country_prefix
            notification.rate_multiplier = recipient_info.rate_multiplier
        except InvalidPhoneError as e:
            if job_id:
                formatted_recipient = recipient
                notification.normalised_to = formatted_recipient
                notification.international = False
                notification.phone_prefix = "+44"
                notification.rate_multiplier = 0
                notification.billable_units = 0
                notification.status = NOTIFICATION_VALIDATION_FAILED
                notification.updated_at = datetime.utcnow()
            else:
                raise e

    elif notification_type == EMAIL_TYPE:
        notification.normalised_to = format_email_address(notification.to)
    elif notification_type == LETTER_TYPE:
        notification.postage = postage
        notification.international = postage in INTERNATIONAL_POSTAGE_TYPES
        notification.normalised_to = "".join(notification.to.split()).lower()

    # if simulated create a Notification model to return but do not persist the Notification to the dB
    if not simulated:
        dao_create_notification(notification)
        increment_daily_limit_cache(
            service.id,
            notification_type,
            key_type,
            international_sms=notification.international,
        )

    return notification


def increment_daily_limit_cache(service_id, notification_type, key_type, international_sms=False):
    if key_type == KEY_TYPE_TEST or not current_app.config["REDIS_ENABLED"]:
        return

    for notification_type_ in [None, notification_type]:
        cache_key = redis.daily_limit_cache_key(service_id, notification_type=notification_type_)
        if redis_store.get(cache_key) is None:
            # if cache does not exist set the cache to 1 with an expiry of 24 hours,
            # The cache should be set by the time we create the notification
            # but in case it is this will make sure the expiry is set to 24 hours,
            # where if we let the incr method create the cache it will be set a ttl.
            redis_store.set(cache_key, 1, ex=86400)
        else:
            redis_store.incr(cache_key)

    if international_sms:
        _increment_international_sms_daily_limit_cache(service_id)


def _increment_international_sms_daily_limit_cache(service_id):
    cache_key = redis.daily_limit_cache_key(service_id, notification_type="international-sms")
    if redis_store.get(cache_key) is None:
        # if cache does not exist set the cache to 1 with an expiry of 24 hours,
        # The cache should be set by the time we create the notification
        # but in case it is this will make sure the expiry is set to 24 hours,
        # where if we let the incr method create the cache it will be set a ttl.
        redis_store.set(cache_key, 1, ex=86400)
    else:
        redis_store.incr(cache_key)


def send_notification_to_queue_detached(key_type, notification_type, notification_id, queue=None):
    if key_type == KEY_TYPE_TEST:
        queue = QueueNames.RESEARCH_MODE

    if notification_type == SMS_TYPE:
        if not queue:
            queue = QueueNames.SEND_SMS
        deliver_task = provider_tasks.deliver_sms
    if notification_type == EMAIL_TYPE:
        if not queue:
            queue = QueueNames.SEND_EMAIL
        deliver_task = provider_tasks.deliver_email
    if notification_type == LETTER_TYPE:
        if not queue:
            queue = QueueNames.CREATE_LETTERS_PDF
        deliver_task = get_pdf_for_templated_letter

    try:
        deliver_task.apply_async([str(notification_id)], queue=queue)
    except Exception:
        dao_delete_notifications_by_id(notification_id)
        raise

    current_app.logger.debug("%s %s sent to the %s queue for delivery", notification_type, notification_id, queue)


def send_notification_to_queue(notification, queue=None):
    send_notification_to_queue_detached(notification.key_type, notification.notification_type, notification.id, queue)


def simulated_recipient(to_address, notification_type):
    if notification_type == SMS_TYPE:
        formatted_simulated_numbers = [
            parse_and_format_phone_number(number) for number in current_app.config["SIMULATED_SMS_NUMBERS"]
        ]
        return to_address in formatted_simulated_numbers
    else:
        return to_address in current_app.config["SIMULATED_EMAIL_ADDRESSES"]
