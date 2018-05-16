from datetime import datetime

from notifications_utils.statsd_decorators import statsd

from app import db
from app.dao.dao_utils import transactional
from app.dao.date_util import get_month_start_and_end_date_in_utc, get_financial_year
from app.dao.notification_usage_dao import get_billing_data_for_month
from app.models import (
    SMS_TYPE,
    EMAIL_TYPE,
    LETTER_TYPE,
    MonthlyBilling,
    NotificationHistory
)
from app.utils import convert_utc_to_bst


def get_service_ids_that_need_billing_populated(start_date, end_date):
    return db.session.query(
        NotificationHistory.service_id
    ).filter(
        NotificationHistory.created_at >= start_date,
        NotificationHistory.created_at <= end_date,
        NotificationHistory.notification_type.in_([SMS_TYPE, EMAIL_TYPE, LETTER_TYPE]),
        NotificationHistory.billable_units != 0
    ).distinct().all()


@statsd(namespace="dao")
def create_or_update_monthly_billing(service_id, billing_month):
    start_date, end_date = get_month_start_and_end_date_in_utc(billing_month)
    _update_monthly_billing(service_id, start_date, end_date, SMS_TYPE)
    _update_monthly_billing(service_id, start_date, end_date, EMAIL_TYPE)
    _update_monthly_billing(service_id, start_date, end_date, LETTER_TYPE)


def _monthly_billing_data_to_json(billing_data):
    results = []
    if billing_data:
        # total cost must take into account the free allowance.
        # might be a good idea to capture free allowance in this table
        results = [{
            "billing_units": x.billing_units,
            "rate_multiplier": x.rate_multiplier,
            "international": x.international,
            "rate": x.rate,
            "total_cost": (x.billing_units * x.rate_multiplier) * x.rate
        } for x in billing_data]
    return results


@statsd(namespace="dao")
@transactional
def _update_monthly_billing(service_id, start_date, end_date, notification_type):
    billing_data = get_billing_data_for_month(
        service_id=service_id,
        start_date=start_date,
        end_date=end_date,
        notification_type=notification_type
    )
    monthly_totals = _monthly_billing_data_to_json(billing_data)
    row = get_monthly_billing_entry(service_id, start_date, notification_type)
    if row:
        row.monthly_totals = monthly_totals
        row.updated_at = datetime.utcnow()
    else:
        row = MonthlyBilling(
            service_id=service_id,
            notification_type=notification_type,
            monthly_totals=monthly_totals,
            start_date=start_date,
            end_date=end_date
        )

    db.session.add(row)


def get_monthly_billing_entry(service_id, start_date, notification_type):
    entry = MonthlyBilling.query.filter_by(
        service_id=service_id,
        start_date=start_date,
        notification_type=notification_type
    ).first()

    return entry


@statsd(namespace="dao")
def get_yearly_billing_data_for_date_range(
    service_id, start_date, end_date, notification_types
):
    results = db.session.query(
        MonthlyBilling.notification_type,
        MonthlyBilling.monthly_totals,
        MonthlyBilling.start_date,
    ).filter(
        MonthlyBilling.service_id == service_id,
        MonthlyBilling.start_date >= start_date,
        MonthlyBilling.end_date <= end_date,
        MonthlyBilling.notification_type.in_(notification_types)
    ).order_by(
        MonthlyBilling.start_date,
        MonthlyBilling.notification_type,
    ).all()

    return results


@statsd(namespace="dao")
def get_monthly_billing_by_notification_type(service_id, billing_month, notification_type):
    billing_month_in_bst = convert_utc_to_bst(billing_month)
    start_date, _ = get_month_start_and_end_date_in_utc(billing_month_in_bst)
    return get_monthly_billing_entry(service_id, start_date, notification_type)


@statsd(namespace="dao")
def get_billing_data_for_financial_year(service_id, year, notification_types=[SMS_TYPE, EMAIL_TYPE, LETTER_TYPE]):
    now = convert_utc_to_bst(datetime.utcnow())
    start_date, end_date = get_financial_year(year)
    if start_date <= now <= end_date:
        # Update totals to the latest so we include data for today
        create_or_update_monthly_billing(service_id=service_id, billing_month=now)

    results = get_yearly_billing_data_for_date_range(
        service_id, start_date, end_date, notification_types
    )
    return results
