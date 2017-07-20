import uuid
from datetime import datetime

from flask import current_app

from notifications_utils.recipients import (
    get_international_phone_info,
    validate_and_format_phone_number,
    format_email_address
)

from app import redis_store
from app.celery import provider_tasks
from notifications_utils.clients import redis

from app.config import QueueNames
from app.models import SMS_TYPE, Notification, KEY_TYPE_TEST, EMAIL_TYPE, ScheduledNotification
from app.dao.notifications_dao import (dao_create_notification,
                                       dao_delete_notifications_and_history_by_id,
                                       dao_created_scheduled_notification)
from app.v2.errors import BadRequestError
from app.utils import get_template_instance, cache_key_for_service_template_counter, convert_bst_to_utc


def create_content_for_notification(template, personalisation):
    template_object = get_template_instance(template.__dict__, personalisation)
    check_placeholders(template_object)

    return template_object


def check_placeholders(template_object):
    if template_object.missing_data:
        message = 'Template missing personalisation: {}'.format(", ".join(template_object.missing_data))
        raise BadRequestError(fields=[{'template': message}], message=message)


def persist_notification(
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
    created_by_id=None
):
    notification_created_at = created_at or datetime.utcnow()
    if not notification_id and simulated:
        notification_id = uuid.uuid4()
    notification = Notification(
        id=notification_id,
        template_id=template_id,
        template_version=template_version,
        to=recipient,
        service_id=service.id,
        service=service,
        personalisation=personalisation,
        notification_type=notification_type,
        api_key_id=api_key_id,
        key_type=key_type,
        created_at=notification_created_at,
        job_id=job_id,
        job_row_number=job_row_number,
        client_reference=client_reference,
        reference=reference,
        created_by_id=created_by_id
    )

    if notification_type == SMS_TYPE:
        formatted_recipient = validate_and_format_phone_number(recipient, international=True)
        recipient_info = get_international_phone_info(formatted_recipient)
        notification.normalised_to = formatted_recipient
        notification.international = recipient_info.international
        notification.phone_prefix = recipient_info.country_prefix
        notification.rate_multiplier = recipient_info.billable_units
    elif notification_type == EMAIL_TYPE:
        notification.normalised_to = format_email_address(notification.to)

    # if simulated create a Notification model to return but do not persist the Notification to the dB
    if not simulated:
        dao_create_notification(notification)
        if key_type != KEY_TYPE_TEST:
            if redis_store.get(redis.daily_limit_cache_key(service.id)):
                redis_store.incr(redis.daily_limit_cache_key(service.id))
            if redis_store.get_all_from_hash(cache_key_for_service_template_counter(service.id)):
                redis_store.increment_hash_value(cache_key_for_service_template_counter(service.id), template_id)
        current_app.logger.info(
            "{} {} created at {}".format(notification_type, notification_id, notification_created_at)
        )
    return notification


def send_notification_to_queue(notification, research_mode, queue=None):
    if research_mode or notification.key_type == KEY_TYPE_TEST:
        queue = QueueNames.RESEARCH_MODE
    elif not queue:
        queue = QueueNames.SEND

    if notification.notification_type == SMS_TYPE:
        deliver_task = provider_tasks.deliver_sms
    if notification.notification_type == EMAIL_TYPE:
        deliver_task = provider_tasks.deliver_email

    try:
        deliver_task.apply_async([str(notification.id)], queue=queue)
    except Exception:
        dao_delete_notifications_and_history_by_id(notification.id)
        raise

    current_app.logger.info(
        "{} {} sent to the {} queue for delivery".format(notification.notification_type,
                                                         notification.id,
                                                         queue))


def simulated_recipient(to_address, notification_type):
    if notification_type == SMS_TYPE:
        formatted_simulated_numbers = [
            validate_and_format_phone_number(number) for number in current_app.config['SIMULATED_SMS_NUMBERS']
        ]
        return to_address in formatted_simulated_numbers
    else:
        return to_address in current_app.config['SIMULATED_EMAIL_ADDRESSES']


def persist_scheduled_notification(notification_id, scheduled_for):
    scheduled_datetime = convert_bst_to_utc(datetime.strptime(scheduled_for, "%Y-%m-%d %H:%M"))
    scheduled_notification = ScheduledNotification(notification_id=notification_id,
                                                   scheduled_for=scheduled_datetime)
    dao_created_scheduled_notification(scheduled_notification)
