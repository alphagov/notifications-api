from datetime import datetime, timedelta

from flask import current_app
from notifications_utils.statsd_decorators import statsd
from notifications_utils.timezones import convert_utc_to_bst

from app import notify_celery
from app.config import QueueNames
from app.cronitor import cronitor
from app.dao.fact_billing_dao import (
    fetch_billing_data_for_day,
    update_fact_billing
)
from app.dao.fact_notification_status_dao import fetch_notification_status_for_day, update_fact_notification_status
from app.celery.nightly_tasks import (
    delete_sms_notifications_older_than_retention,
    delete_email_notifications_older_than_retention,
    delete_letter_notifications_older_than_retention
)


@notify_celery.task(name="create-nightly-billing")
@cronitor("create-nightly-billing")
@statsd(namespace="tasks")
def create_nightly_billing(day_start=None):
    # day_start is a datetime.date() object. e.g.
    # up to 10 days of data counting back from day_start is consolidated
    if day_start is None:
        day_start = convert_utc_to_bst(datetime.utcnow()).date() - timedelta(days=1)
    else:
        # When calling the task its a string in the format of "YYYY-MM-DD"
        day_start = datetime.strptime(day_start, "%Y-%m-%d").date()
    for i in range(0, 10):
        process_day = day_start - timedelta(days=i)

        transit_data = fetch_billing_data_for_day(process_day=process_day)

        for data in transit_data:
            update_fact_billing(data, process_day)

        current_app.logger.info(
            "create-nightly-billing task complete. {} rows updated for day: {}".format(len(transit_data), process_day))


@notify_celery.task(name="create-nightly-notification-status")
@cronitor("create-nightly-notification-status")
@statsd(namespace="tasks")
def create_nightly_notification_status(day_start=None):
    # day_start is a datetime.date() object. e.g.
    # 4 days of data counting back from day_start is consolidated
    if day_start is None:
        day_start = convert_utc_to_bst(datetime.utcnow()).date() - timedelta(days=1)
    else:
        # When calling the task its a string in the format of "YYYY-MM-DD"
        day_start = datetime.strptime(day_start, "%Y-%m-%d").date()
    for i in range(0, 10):
        process_day = day_start - timedelta(days=i)

        transit_data = fetch_notification_status_for_day(process_day=process_day)

        update_fact_notification_status(transit_data, process_day)

        current_app.logger.info(
            "create-nightly-notification-status task: {} rows updated for day: {}".format(
                len(transit_data), process_day
            )
        )

    # delete jobs need to happen after nightly notification status is recorded to avoid conflict between the two tasks
    delete_email_notifications_older_than_retention.apply_async(queue=QueueNames.PERIODIC)
    delete_sms_notifications_older_than_retention.apply_async(queue=QueueNames.PERIODIC)
    delete_letter_notifications_older_than_retention.apply_async(queue=QueueNames.PERIODIC)
