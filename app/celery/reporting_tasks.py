from datetime import datetime, timedelta

from flask import current_app
from notifications_utils.timezones import convert_utc_to_bst

from app import notify_celery
from app.config import QueueNames
from app.cronitor import cronitor
from app.dao.fact_billing_dao import (
    fetch_billing_data_for_day,
    update_fact_billing,
)
from app.dao.fact_notification_status_dao import (
    fetch_notification_status_for_day,
    update_fact_notification_status,
)
from app.models import EMAIL_TYPE, LETTER_TYPE, SMS_TYPE


@notify_celery.task(name="create-nightly-billing")
@cronitor("create-nightly-billing")
def create_nightly_billing(day_start=None):
    # day_start is a datetime.date() object. e.g.
    # up to 4 days of data counting back from day_start is consolidated
    if day_start is None:
        day_start = convert_utc_to_bst(datetime.utcnow()).date() - timedelta(days=1)
    else:
        # When calling the task its a string in the format of "YYYY-MM-DD"
        day_start = datetime.strptime(day_start, "%Y-%m-%d").date()
    for i in range(0, 4):
        process_day = (day_start - timedelta(days=i)).isoformat()

        create_nightly_billing_for_day.apply_async(
            kwargs={'process_day': process_day},
            queue=QueueNames.REPORTING
        )
        current_app.logger.info(
            f"create-nightly-billing task: create-nightly-billing-for-day task created for {process_day}"
        )


@notify_celery.task(name="create-nightly-billing-for-day")
def create_nightly_billing_for_day(process_day):
    process_day = datetime.strptime(process_day, "%Y-%m-%d").date()
    current_app.logger.info(
        f'create-nightly-billing-for-day task for {process_day}: started'
    )

    start = datetime.utcnow()
    transit_data = fetch_billing_data_for_day(process_day=process_day)
    end = datetime.utcnow()

    current_app.logger.info(
        f'create-nightly-billing-for-day task for {process_day}: data fetched in {(end - start).seconds} seconds'
    )

    for data in transit_data:
        update_fact_billing(data, process_day)

    current_app.logger.info(
        f"create-nightly-billing-for-day task for {process_day}: "
        f"task complete. {len(transit_data)} rows updated"
    )


@notify_celery.task(name="create-nightly-notification-status")
@cronitor("create-nightly-notification-status")
def create_nightly_notification_status():
    """
    Aggregate notification statuses into rows in ft_notification_status.
    In order to minimise effort, this task assumes that:

      - Email + SMS statuses don't change after 3 days. This is currently true
        because all outstanding email / SMS are "timed out" after 3 days, and
        we reject delivery receipts after this point.

      - Letter statuses don't change after 9 days. There's no "timeout" for
        letters but this is the longest we've had to cope with in the past - due
        to major issues with our print provider.

    Because the time range of the task exceeds the minimum possible retention
    period (3 days), we need to choose which table to query for each service.

    The aggregation happens for 1 extra day in case:

      - This task or the "timeout" task fails to run.

      - Data is (somehow) still in transit to the history table, which would
        mean the aggregated results are temporarily incorrect.
    """

    yesterday = convert_utc_to_bst(datetime.utcnow()).date() - timedelta(days=1)

    # email and sms
    for i in range(4):
        process_day = yesterday - timedelta(days=i)
        for notification_type in [SMS_TYPE, EMAIL_TYPE]:
            create_nightly_notification_status_for_day.apply_async(
                kwargs={'process_day': process_day.isoformat(), 'notification_type': notification_type},
                queue=QueueNames.REPORTING
            )
            current_app.logger.info(
                f"create-nightly-notification-status task: create-nightly-notification-status-for-day task created "
                f"for type {notification_type} for {process_day}"
            )

    # letters
    for i in range(10):
        process_day = yesterday - timedelta(days=i)
        create_nightly_notification_status_for_day.apply_async(
            kwargs={'process_day': process_day.isoformat(), 'notification_type': LETTER_TYPE},
            queue=QueueNames.REPORTING
        )
        current_app.logger.info(
            f"create-nightly-notification-status task: create-nightly-notification-status-for-day task created "
            f"for type letter for {process_day}"
        )


@notify_celery.task(name="create-nightly-notification-status-for-day")
def create_nightly_notification_status_for_day(process_day, notification_type):
    process_day = datetime.strptime(process_day, "%Y-%m-%d").date()
    current_app.logger.info(
        f'create-nightly-notification-status-for-day task for {process_day} type {notification_type}: started'
    )

    start = datetime.utcnow()
    transit_data = fetch_notification_status_for_day(process_day=process_day, notification_type=notification_type)
    end = datetime.utcnow()
    current_app.logger.info(
        f'create-nightly-notification-status-for-day task for {process_day} type {notification_type}: '
        f'data fetched in {(end - start).seconds} seconds'
    )

    update_fact_notification_status(transit_data, process_day, notification_type)

    current_app.logger.info(
        f'create-nightly-notification-status-for-day task for {process_day} type {notification_type}: '
        f'task complete - {len(transit_data)} rows updated'
    )
