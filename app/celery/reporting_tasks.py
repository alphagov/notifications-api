from datetime import datetime, timedelta, time

from flask import current_app
from notifications_utils.statsd_decorators import statsd

from app import notify_celery
from app.dao.fact_billing_dao import (
    fetch_billing_data,
    update_fact_billing
)
from app.utils import convert_bst_to_utc


@notify_celery.task(name="create-nightly-billing")
@statsd(namespace="tasks")
def create_nightly_billing(day_start=None):
    # day_start is a datetime.date() object. e.g.
    # 3 days of data counting back from day_start is consolidated
    if day_start is None:
        day_start = datetime.today() - timedelta(days=1)

    for i in range(0, 3):
        process_day = day_start - timedelta(days=i)
        ds = convert_bst_to_utc(datetime.combine(process_day, time.min))
        de = convert_bst_to_utc(datetime.combine(process_day + timedelta(days=1), time.min))

        transit_data = fetch_billing_data(start_date=ds, end_date=de)

        updated_records = 0
        inserted_records = 0

        for data in transit_data:
            inserted_records, updated_records = update_fact_billing(data,
                                                                    inserted_records,
                                                                    process_day,
                                                                    updated_records)

        current_app.logger.info('ft_billing {} to {}: {} rows updated, {} rows inserted'
                                .format(ds, de, updated_records, inserted_records))
