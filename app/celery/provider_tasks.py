from flask import current_app
from notifications_utils.recipients import InvalidEmailError
from sqlalchemy.orm.exc import NoResultFound

from app import notify_celery
from app.celery import QueueNames
from app.dao import notifications_dao
from app.dao.notifications_dao import update_notification_status_by_id
from app.statsd_decorators import statsd
from app.delivery import send_to_providers


@notify_celery.task(bind=True, name="deliver_sms", max_retries=48, default_retry_delay=300)
@statsd(namespace="tasks")
def deliver_sms(self, notification_id):
    try:
        notification = notifications_dao.get_notification_by_id(notification_id)
        if not notification:
            raise NoResultFound()
        send_to_providers.send_sms_to_provider(notification)
    except Exception as e:
        try:
            current_app.logger.exception(
                "SMS notification delivery for id: {} failed".format(notification_id)
            )
            self.retry(queue=QueueNames.RETRY)
        except self.MaxRetriesExceededError:
            current_app.logger.exception(
                "RETRY FAILED: task send_sms_to_provider failed for notification {}".format(notification_id),
            )
            update_notification_status_by_id(notification_id, 'technical-failure')


@notify_celery.task(bind=True, name="deliver_email", max_retries=48, default_retry_delay=300)
@statsd(namespace="tasks")
def deliver_email(self, notification_id):
    try:
        notification = notifications_dao.get_notification_by_id(notification_id)
        if not notification:
            raise NoResultFound()
        send_to_providers.send_email_to_provider(notification)
    except InvalidEmailError as e:
        current_app.logger.exception(e)
        update_notification_status_by_id(notification_id, 'technical-failure')
    except Exception as e:
        try:
            current_app.logger.exception(
                "RETRY: Email notification {} failed".format(notification_id)
            )
            self.retry(queue=QueueNames.RETRY)
        except self.MaxRetriesExceededError:
            current_app.logger.error(
                "RETRY FAILED: task send_email_to_provider failed for notification {}".format(notification_id)
            )
            update_notification_status_by_id(notification_id, 'technical-failure')
