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
from app.models import (
    SMS_TYPE,
    EMAIL_TYPE,
    LETTER_TYPE,
)


@notify_celery.task(name="create-nightly-billing")
@cronitor("create-nightly-billing")
@statsd(namespace="tasks")
def create_nightly_billing(day_start=None):
    # day_start is a datetime.date() object. e.g.
    # up to 4 days of data counting back from day_start is consolidated
    if day_start is None:
        day_start = convert_utc_to_bst(datetime.utcnow()).date() - timedelta(days=1)
    else:
        # When calling the task its a string in the format of "YYYY-MM-DD"
        day_start = datetime.strptime(day_start, "%Y-%m-%d").date()
    for i in range(0, 4):
        process_day = day_start - timedelta(days=i)

        create_nightly_billing_for_day.apply_async(
            kwargs={'process_day': process_day.isoformat()},
            queue=QueueNames.REPORTING
        )


@notify_celery.task(name="create-nightly-billing-for-day")
@statsd(namespace="tasks")
def create_nightly_billing_for_day(process_day):
    # When app.celery.scheduled_tasks.purge_high_volume_notifications starts
    # we need to exclude HighVolumeServices from the list.
    process_day = datetime.strptime(process_day, "%Y-%m-%d").date()

    start = datetime.utcnow()
    transit_data = fetch_billing_data_for_day(process_day=process_day)
    end = datetime.utcnow()

    current_app.logger.info(f'create-nightly-billing-for-day {process_day} fetched in {(end - start).seconds} seconds')

    for data in transit_data:
        update_fact_billing(data, process_day)

    current_app.logger.info(
        f"create-nightly-billing-for-day task complete. {len(transit_data)} rows updated for day: {process_day}"
    )


@notify_celery.task(name="create-nightly-notification-status")
@cronitor("create-nightly-notification-status")
@statsd(namespace="tasks")
def create_nightly_notification_status():
    # When app.celery.scheduled_tasks.purge_high_volume_notifications starts
    # we need to exclude HighVolumeServices from the list.
    yesterday = convert_utc_to_bst(datetime.utcnow()).date() - timedelta(days=1)

    # email and sms
    for i in range(4):
        process_day = yesterday - timedelta(days=i)
        for notification_type in [SMS_TYPE, EMAIL_TYPE]:
            create_nightly_notification_status_for_day.apply_async(
                kwargs={'process_day': process_day.isoformat(), 'notification_type': notification_type},
                queue=QueueNames.REPORTING
            )
    # letters get modified for a longer time period than sms and email, so we need to reprocess for more days
    for i in range(10):
        process_day = yesterday - timedelta(days=i)
        create_nightly_notification_status_for_day.apply_async(
            kwargs={'process_day': process_day.isoformat(), 'notification_type': LETTER_TYPE},
            queue=QueueNames.REPORTING
        )


@notify_celery.task(name="create-nightly-notification-status-for-day")
@statsd(namespace="tasks")
def create_nightly_notification_status_for_day(process_day, notification_type):
    # When app.celery.scheduled_tasks.purge_high_volume_notifications starts
    # we need to exclude HighVolumeServices from the list.
    process_day = datetime.strptime(process_day, "%Y-%m-%d").date()

    start = datetime.utcnow()
    transit_data = fetch_notification_status_for_day(process_day=process_day, notification_type=notification_type)
    end = datetime.utcnow()
    current_app.logger.info(
        f'create-nightly-notification-status-for-day {process_day} type {notification_type} task: '
        f'data fetched in {(end - start).seconds} seconds'
    )

    update_fact_notification_status(transit_data, process_day, notification_type)

    current_app.logger.info(
        f'create-nightly-notification-status-for-day {process_day} type {notification_type} task: '
        f'task complete - {len(transit_data)} rows updated'
    )
