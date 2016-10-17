from flask import current_app
from notifications_utils.recipients import InvalidEmailError
from sqlalchemy.orm.exc import NoResultFound

from app import notify_celery
from app.dao import notifications_dao
from app.dao.notifications_dao import update_notification_status_by_id
from app.statsd_decorators import statsd
from app.delivery import send_to_providers


def retry_iteration_to_delay(retry=0):
    """
    :param retry times we have performed a retry
    Given current retry calculate some delay before retrying
    0: 10 seconds
    1: 60 seconds (1 minutes)
    2: 300 seconds (5 minutes)
    3: 3600 seconds (60 minutes)
    4: 14400 seconds (4 hours)
    :param retry (zero indexed):
    :return length to retry in seconds, default 10 seconds
    """

    delays = {
        0: 10,
        1: 60,
        2: 300,
        3: 3600,
        4: 14400
    }

    return delays.get(retry, 10)


@notify_celery.task(bind=True, name="deliver_sms", max_retries=5, default_retry_delay=5)
@statsd(namespace="tasks")
def deliver_sms(self, notification_id):
    try:
        notification = notifications_dao.get_notification_by_id(notification_id)
        if not notification:
            raise NoResultFound()
        send_to_providers.send_sms_to_provider(notification)
    except Exception as e:
        try:
            current_app.logger.error(
                "RETRY: SMS notification {} failed".format(notification_id)
            )
            current_app.logger.exception(e)
            self.retry(queue="retry", countdown=retry_iteration_to_delay(self.request.retries))
        except self.MaxRetriesExceededError:
            current_app.logger.error(
                "RETRY FAILED: task send_sms_to_provider failed for notification {}".format(notification_id),
                e
            )
            update_notification_status_by_id(notification_id, 'technical-failure')


@notify_celery.task(bind=True, name="deliver_email", max_retries=5, default_retry_delay=5)
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
            current_app.logger.error(
                "RETRY: Email notification {} failed".format(notification_id)
            )
            current_app.logger.exception(e)
            self.retry(queue="retry", countdown=retry_iteration_to_delay(self.request.retries))
        except self.MaxRetriesExceededError:
            current_app.logger.error(
                "RETRY FAILED: task send_email_to_provider failed for notification {}".format(notification_id),
                e
            )
            update_notification_status_by_id(notification_id, 'technical-failure')
