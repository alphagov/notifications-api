from datetime import datetime

from flask import current_app

from app import redis_store
from app.celery import provider_tasks
from notifications_utils.clients import redis

from app.dao.notifications_dao import dao_create_notification, dao_delete_notifications_and_history_by_id
from app.models import SMS_TYPE, Notification, KEY_TYPE_TEST, EMAIL_TYPE
from app.v2.errors import BadRequestError, SendNotificationToQueueError
from app.utils import get_template_instance, cache_key_for_service_template_counter


def create_content_for_notification(template, personalisation):
    template_object = get_template_instance(template.__dict__, personalisation)
    check_placeholders(template_object)

    return template_object


def check_placeholders(template_object):
    if template_object.missing_data:
        message = 'Template missing personalisation: {}'.format(", ".join(template_object.missing_data))
        raise BadRequestError(fields=[{'template': message}], message=message)


def persist_notification(template_id,
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
                         notification_id=None,
                         simulated=False,
                         persist=True):

    # if simulated create a Notification model to return but do not persist the Notification to the dB
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
        created_at=created_at or datetime.utcnow(),
        job_id=job_id,
        job_row_number=job_row_number,
        client_reference=reference
    )
    if not simulated:
        if persist:
            dao_create_notification(notification)
        if redis_store.get(redis.daily_limit_cache_key(service.id)):
            redis_store.incr(redis.daily_limit_cache_key(service.id))
        if redis_store.get_all_from_hash(cache_key_for_service_template_counter(service.id)):
            redis_store.increment_hash_value(cache_key_for_service_template_counter(service.id), template_id)
        current_app.logger.info(
            "{} {} created at {}".format(notification.notification_type, notification.id, notification.created_at)
        )
    return notification


def send_notification_to_queue(notification, research_mode, queue=None):
    if research_mode or notification.key_type == KEY_TYPE_TEST:
        queue = 'research-mode'
    elif not queue:
        if notification.notification_type == SMS_TYPE:
            queue = 'send-sms'
        if notification.notification_type == EMAIL_TYPE:
            queue = 'send-email'

    if notification.notification_type == SMS_TYPE:
        deliver_task = provider_tasks.deliver_sms
    if notification.notification_type == EMAIL_TYPE:
        deliver_task = provider_tasks.deliver_email

    try:
        deliver_task.apply_async([str(notification.id)], queue=queue)
    except Exception as e:
        current_app.logger.exception(e)
        dao_delete_notifications_and_history_by_id(notification.id)
        raise SendNotificationToQueueError()

    current_app.logger.info(
        "{} {} sent to the {} queue for delivery".format(notification.notification_type,
                                                         notification.id,
                                                         queue))


def simulated_recipient(to_address, notification_type):
    return (to_address in current_app.config['SIMULATED_SMS_NUMBERS']
            if notification_type == SMS_TYPE
            else to_address in current_app.config['SIMULATED_EMAIL_ADDRESSES'])
