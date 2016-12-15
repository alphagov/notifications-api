from datetime import datetime

from flask import current_app

from app import redis_store
from app.celery import provider_tasks
from notifications_utils.clients import redis
from app.dao.notifications_dao import dao_create_notification, dao_delete_notifications_and_history_by_id
from app.models import SMS_TYPE, Notification, KEY_TYPE_TEST, EMAIL_TYPE
from app.v2.errors import BadRequestError, SendNotificationToQueueError
from app.utils import get_template_instance


def create_content_for_notification(template, personalisation):
    template_object = get_template_instance(template.__dict__, personalisation)
    check_placeholders(template_object)

    return template_object


def check_placeholders(template_object):
    if template_object.missing_data:
        message = 'Template missing personalisation: {}'.format(", ".join(template_object.missing_data))
        raise BadRequestError(fields=[{'template': message}], message=message)

    if template_object.additional_data:
        message = 'Template personalisation not needed for template: {}'.format(
            ", ".join(template_object.additional_data))
        raise BadRequestError(fields=[{'template': message}], message=message)


def persist_notification(template_id,
                         template_version,
                         recipient,
                         service_id,
                         personalisation,
                         notification_type,
                         api_key_id,
                         key_type,
                         created_at=None,
                         job_id=None,
                         job_row_number=None,
                         reference=None,
                         notification_id=None):
    notification = Notification(
        id=notification_id,
        template_id=template_id,
        template_version=template_version,
        to=recipient,
        service_id=service_id,
        personalisation=personalisation,
        notification_type=notification_type,
        api_key_id=api_key_id,
        key_type=key_type,
        created_at=created_at or datetime.utcnow(),
        job_id=job_id,
        job_row_number=job_row_number,
        client_reference=reference
    )
    dao_create_notification(notification)
    redis_store.incr(redis.daily_limit_cache_key(service_id))
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
        "{} {} created at {}".format(notification.notification_type, notification.id, notification.created_at)
    )
