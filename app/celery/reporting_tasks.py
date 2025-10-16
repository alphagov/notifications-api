from datetime import UTC, datetime, timedelta

from flask import current_app
from notifications_utils.timezones import convert_utc_to_bst

from app import notify_celery, redis_store
from app.config import QueueNames
from app.constants import EMAIL_TYPE, LETTER_TYPE, SMS_TYPE, CacheKeys
from app.cronitor import cronitor
from app.dao.fact_billing_dao import (
    fetch_billing_data_for_day,
    update_ft_billing,
    update_ft_billing_letter_despatch,
)
from app.dao.fact_notification_status_dao import update_fact_notification_status
from app.dao.notifications_dao import get_service_ids_with_notifications_on_date


@notify_celery.task(name="create-nightly-billing")
@cronitor("create-nightly-billing")
def create_nightly_billing(
    day_start=None,
    n_days=10,
    stagger_total_period_seconds=timedelta(minutes=5).seconds,
):
    # day_start is a datetime.date() object. i.e. up to n_days days of data counting
    # back from day_start is consolidated
    if day_start is None:
        day_start = convert_utc_to_bst(datetime.utcnow()).date() - timedelta(days=1)
    else:
        # When calling the task its a string in the format of "YYYY-MM-DD"
        day_start = datetime.strptime(day_start, "%Y-%m-%d").date()
    for i in range(n_days):
        process_day = (day_start - timedelta(days=i)).isoformat()

        create_or_update_ft_billing_for_day.apply_async(
            kwargs={"process_day": process_day},
            queue=QueueNames.REPORTING,
            # starting all the spawned queries at the same time uses a lot of
            # database resources
            countdown=stagger_total_period_seconds * i / n_days,
        )
        current_app.logger.info(
            "create-nightly-billing task: create-or-update-ft-billing-for-day task created for %s", process_day
        )

        create_or_update_ft_billing_letter_despatch_for_day.apply_async(
            kwargs={"process_day": process_day}, queue=QueueNames.REPORTING
        )
        current_app.logger.info(
            "create-nightly-billing task: create-or-update-ft-billing-letter-despatch-for-day task created for %s",
            process_day,
        )


@notify_celery.task(name="update-ft-billing-for-today")
@cronitor("update-ft-billing-for-today")
def update_ft_billing_for_today():
    process_day = convert_utc_to_bst(datetime.utcnow()).date().isoformat()
    create_or_update_ft_billing_for_day(process_day=process_day)
    redis_store.set(CacheKeys.FT_BILLING_FOR_TODAY_UPDATED_AT_UTC_ISOFORMAT, datetime.now(UTC).isoformat())


@notify_celery.task(name="create-or-update-ft-billing-for-day")
def create_or_update_ft_billing_for_day(process_day: str):
    process_date = datetime.strptime(process_day, "%Y-%m-%d").date()
    current_app.logger.info("create-or-update-ft-billing-for-day task for %s: started", process_date)

    start = datetime.utcnow()
    billing_data = fetch_billing_data_for_day(process_day=process_date)
    end = datetime.utcnow()

    current_app.logger.info(
        "create-or-update-ft-billing-for-day task for %s: data fetched in %s seconds",
        process_date,
        (end - start).seconds,
    )

    update_ft_billing(billing_data, process_date)

    current_app.logger.info(
        "create-nightly-billing-for-day task for %s: task complete. %s rows updated", process_date, len(billing_data)
    )


@notify_celery.task(name="create-or-update-ft-billing-letter-despatch-for-day")
def create_or_update_ft_billing_letter_despatch_for_day(process_day: str):
    process_date = datetime.strptime(process_day, "%Y-%m-%d").date()
    current_app.logger.info("create-or-update-ft-billing-letter-despatch-for-day task for %s: started", process_date)

    created, deleted = update_ft_billing_letter_despatch(process_date)

    current_app.logger.info(
        "create-or-update-ft-billing-letter-despatch-for-day task for %(date)s: task complete. "
        "%(deleted)s old row(s) deleted, and %(created)s row(s) created.",
        {"date": process_date, "deleted": deleted, "created": created},
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

    for notification_type in [SMS_TYPE, EMAIL_TYPE, LETTER_TYPE]:
        days = 10 if notification_type == LETTER_TYPE else 4

        for i in range(days):
            process_day = yesterday - timedelta(days=i)

            relevant_service_ids = get_service_ids_with_notifications_on_date(notification_type, process_day)

            for service_id in relevant_service_ids:
                create_nightly_notification_status_for_service_and_day.apply_async(
                    kwargs={
                        "process_day": process_day.isoformat(),
                        "notification_type": notification_type,
                        "service_id": service_id,
                    },
                    queue=QueueNames.REPORTING,
                )


@notify_celery.task(name="create-nightly-notification-status-for-service-and-day")
def create_nightly_notification_status_for_service_and_day(process_day, service_id, notification_type):
    process_day = datetime.strptime(process_day, "%Y-%m-%d").date()

    start = datetime.utcnow()
    update_fact_notification_status(process_day=process_day, notification_type=notification_type, service_id=service_id)

    end = datetime.utcnow()
    current_app.logger.info(
        (
            "create-nightly-notification-status-for-service-and-day task update for "
            "%(service_id)s, %(type)s for %(date)s: updated in %(duration)s seconds"
        ),
        {"service_id": service_id, "type": notification_type, "date": process_day, "duration": (end - start).seconds},
    )
