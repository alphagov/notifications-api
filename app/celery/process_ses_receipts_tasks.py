from datetime import datetime, timedelta

import iso8601
from celery.exceptions import Retry
from flask import current_app, json
from sqlalchemy.orm.exc import NoResultFound

from app import notify_celery, statsd_client
from app.clients.email.aws_ses import get_aws_responses
from app.config import QueueNames
from app.constants import NOTIFICATION_PENDING, NOTIFICATION_SENDING
from app.dao import notifications_dao
from app.notifications.notifications_ses_callback import (
    _check_and_queue_complaint_callback_task,
    check_and_queue_callback_task,
    determine_notification_bounce_type,
    handle_complaint,
)


@notify_celery.task(bind=True, name="process-ses-result", max_retries=5, default_retry_delay=300)
def process_ses_results(self, response):
    try:
        ses_message = json.loads(response["Message"])
        notification_type = ses_message["notificationType"]
        bounce_message = None

        if notification_type == "Bounce":
            notification_type, bounce_message = determine_notification_bounce_type(notification_type, ses_message)
        elif notification_type == "Complaint":
            _check_and_queue_complaint_callback_task(*handle_complaint(ses_message))
            return True

        aws_response_dict = get_aws_responses(notification_type)

        notification_status = aws_response_dict["notification_status"]
        reference = ses_message["mail"]["messageId"]

        try:
            notification = notifications_dao.dao_get_notification_or_history_by_reference(reference=reference)
        except NoResultFound:
            message_time = iso8601.parse_date(ses_message["mail"]["timestamp"]).replace(tzinfo=None)
            if datetime.utcnow() - message_time < timedelta(minutes=5):
                current_app.logger.info(
                    "notification not found for reference: %s (update to %s). "
                    "Callback may have arrived before notification was persisted to the DB. Adding task to retry queue",
                    reference,
                    notification_status,
                )
                self.retry(queue=QueueNames.RETRY)
            else:
                current_app.logger.warning(
                    "notification not found for reference: %s (update to %s)", reference, notification_status
                )
            return

        if bounce_message:
            current_app.logger.info(
                "SES bounce for notification ID %s",
                notification.id,
                extra=dict(bounce_message=json.dumps(bounce_message)),
            )
        else:
            current_app.logger.info(
                "SES successful delivery for notification ID %s",
                notification.id,
            )

        if notification.status not in [NOTIFICATION_SENDING, NOTIFICATION_PENDING]:
            notifications_dao._duplicate_update_warning(notification=notification, status=notification_status)
            return
        else:
            notifications_dao.dao_update_notifications_by_reference(
                references=[reference], update_dict={"status": notification_status}
            )

        statsd_client.incr("callback.ses.{}".format(notification_status))

        if notification.sent_at:
            statsd_client.timing_with_dates(
                f"callback.ses.{notification_status}.elapsed-time", datetime.utcnow(), notification.sent_at
            )

        check_and_queue_callback_task(notification)

        return True

    except Retry:
        raise

    except Exception as e:
        current_app.logger.exception("Error processing SES results: %s", type(e))
        self.retry(queue=QueueNames.RETRY)
