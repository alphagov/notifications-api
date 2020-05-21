from datetime import datetime, timedelta, date

import iso8601
from flask import current_app
from notifications_utils.statsd_decorators import statsd
from notifications_utils.timezones import convert_utc_to_bst

from app.utils import get_london_midnight_in_utc
from app import notify_celery, redis_store
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


# this is how long we store the task run timestamp in redis before expiring it. it gives us time to work out what
# happened after a long weekend, but we shouldn't really care about tasks older than that.
FOUR_DAYS_IN_SECONDS = int(timedelta(days=4).total_seconds())


def _get_nightly_task_redis_key(task_name, task_kwargs):
    """
    Redis key that identifies a run of a given daily task. EG:
    task_last_run_timestamp_create-nightly-billing-for-day_process_day_2020-04-04
    """
    redis_key = f'task_last_run_timestamp_{task_name}'
    # make sure we sort the kwargs so the string is always consistent
    for key, value in sorted(task_kwargs.items()):
        if isinstance(value, date):
            value = value.strftime("%Y-%m-%d")
        redis_key += f'_{key}_{value}'
    return redis_key


def _task_has_run_today(task_name, task_kwargs):
    if not current_app.config['REDIS_ENABLED']:
        return True

    redis_key = _get_nightly_task_redis_key(task_name, task_kwargs)

    day_start = get_london_midnight_in_utc(datetime.utcnow())

    # if its not in redis set to datetime.min so we assume it has never been run and re-trigger it
    val_from_redis = redis_store.get(redis_key)
    last_ran_timestamp = iso8601.parse_date(val_from_redis).replace(tzinfo=None) if val_from_redis else datetime.min
    return last_ran_timestamp > day_start


@notify_celery.task(name="create-nightly-billing")
@cronitor("create-nightly-billing")
@statsd(namespace="tasks")
def create_nightly_billing(day_start=None, only_run_missing_days=False):
    current_app.logger.info("create-nightly-billing task: started")
    # day_start is a datetime.date() object. e.g.
    # up to 4 days of data counting back from day_start is consolidated
    if day_start is None:
        day_start = convert_utc_to_bst(datetime.utcnow()).date() - timedelta(days=1)
    else:
        # When calling the task its a string in the format of "YYYY-MM-DD"
        day_start = datetime.strptime(day_start, "%Y-%m-%d").date()

    for i in range(0, 4):
        process_day = (day_start - timedelta(days=i)).isoformat()
        kwargs = {'process_day': process_day}

        if only_run_missing_days:
            child_task_name = create_nightly_billing_for_day.name
            if _task_has_run_today(child_task_name, kwargs):
                # skip this task
                continue
            else:
                current_app.logger.warning(f'task not completed retriggering task {child_task_name} with args {kwargs}')

        create_nightly_billing_for_day.apply_async(kwargs=kwargs, queue=QueueNames.REPORTING)
        current_app.logger.info(
            f"create-nightly-billing task: create-nightly-billing-for-day task created for {process_day}"
        )


@notify_celery.task(bind=True, name="create-nightly-billing-for-day")
@statsd(namespace="tasks")
def create_nightly_billing_for_day(self, process_day):
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

    if current_app.config['REDIS_ENABLED']:
        redis_key = _get_nightly_task_redis_key(self.name, task_kwargs={'process_day': process_day})
        redis_store.set(redis_key, datetime.utcnow().isoformat(), ex=FOUR_DAYS_IN_SECONDS)


@notify_celery.task(name="create-nightly-notification-status")
@cronitor("create-nightly-notification-status")
@statsd(namespace="tasks")
def create_nightly_notification_status(only_run_missing_days=False):
    current_app.logger.info("create-nightly-notification-status task: started")
    yesterday = convert_utc_to_bst(datetime.utcnow()).date() - timedelta(days=1)

    tasks_to_run = []

    # email and sms
    for i in range(4):
        process_day = yesterday - timedelta(days=i)
        for notification_type in [SMS_TYPE, EMAIL_TYPE]:
            tasks_to_run.append({'process_day': process_day.isoformat(), 'notification_type': notification_type})

    # letters get modified for a longer time period than sms and email, so we need to reprocess for more days
    for i in range(10):
        process_day = yesterday - timedelta(days=i)
        tasks_to_run.append({'process_day': process_day.isoformat(), 'notification_type': LETTER_TYPE})

    child_task_name = create_nightly_notification_status_for_day.name
    for kwargs in tasks_to_run:
        if only_run_missing_days:
            if _task_has_run_today(child_task_name, kwargs):
                # skip this task
                continue
            else:
                current_app.logger.warning(
                    f'task not completed since midnight: {child_task_name} task with args {kwargs}'
                )

        create_nightly_notification_status_for_day.apply_async(kwargs=kwargs, queue=QueueNames.REPORTING)
        current_app.logger.info(
            f"create-nightly-notification-status task: {child_task_name} task created "
            f"for type {kwargs['notification_type']} for {kwargs['process_day']}"
        )


@notify_celery.task(bind=True, name="create-nightly-notification-status-for-day")
@statsd(namespace="tasks")
def create_nightly_notification_status_for_day(self, process_day, notification_type):
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

    if current_app.config['REDIS_ENABLED']:
        redis_key = _get_nightly_task_redis_key(
            self.name,
            task_kwargs={'notification_type': notification_type, 'process_day': process_day}
        )
        redis_store.set(redis_key, datetime.utcnow().isoformat(), ex=FOUR_DAYS_IN_SECONDS)


@notify_celery.task(name='rerun-failed-nightly-tasks')
def rerun_failed_nightly_tasks():
    create_nightly_billing(only_run_missing_days=True)
    create_nightly_notification_status(only_run_missing_days=True)
