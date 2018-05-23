from datetime import datetime, timedelta

from flask import current_app
from notifications_utils.statsd_decorators import statsd

from app import notify_celery
from app.dao.fact_billing_dao import (
    fetch_billing_data_for_day,
    update_fact_billing
)


@notify_celery.task(name="create-nightly-billing")
@statsd(namespace="tasks")
def create_nightly_billing(day_start=None):
    # day_start is a datetime.date() object. e.g.
    # 3 days of data counting back from day_start is consolidated
    if day_start is None:
        day_start = datetime.today() - timedelta(days=1)
    else:
        # When calling the task its a string in the format of "YYYY-MM-DD"
        day_start = datetime.strptime(day_start, "%Y-%m-%d")
    for i in range(0, 3):
        process_day = day_start - timedelta(days=i)

        transit_data = fetch_billing_data_for_day(process_day=process_day)

        for data in transit_data:
            update_fact_billing(data, process_day)

        current_app.logger.info(
            "create-nightly-billing task complete. {} rows updated for day: {}".format(len(transit_data), process_day))
