from datetime import datetime, timedelta
from sqlalchemy import func

from app import db
from app.dao.date_util import get_month_start_and_end_date_in_utc, get_financial_year
from app.models import FactBilling
from app.utils import convert_utc_to_bst


def fetch_annual_billing_by_month(service_id, billing_month, notification_type):
    billing_month_in_bst = convert_utc_to_bst(billing_month)
    start_date, end_date = get_month_start_and_end_date_in_utc(billing_month_in_bst)

    monthly_data = db.session.query(
        func.sum(FactBilling.notifications_sent).label('notifications_sent'),
        func.sum(FactBilling.billable_units).label('billing_units'),
        FactBilling.service_id,
        FactBilling.notification_type,
        FactBilling.rate,
        FactBilling.rate_multiplier,
        FactBilling.international
    ).filter(
        FactBilling.notification_type == notification_type,
        FactBilling.service_id == service_id,
        FactBilling.bst_date >= start_date,
        FactBilling.bst_date <= end_date
    ).group_by(
        FactBilling.service_id,
        FactBilling.notification_type,
        FactBilling.rate,
        FactBilling.rate_multiplier,
        FactBilling.international
    ).all()

    return monthly_data, start_date


def need_deltas(start_date, end_date, service_id, notification_type):
    max_fact_billing_date = db.session.query(
        func.max(FactBilling.bst_date)
    ).filter(
        FactBilling.notification_type == notification_type,
        FactBilling.service_id == service_id,
        FactBilling.bst_date >= start_date,
        FactBilling.bst_date <= end_date
    ).one()
    print(max_fact_billing_date)
    return max_fact_billing_date < end_date


def fetch_annual_billing_for_year(service_id, year):
    year_start_date, year_end_date = get_financial_year(year)
    utcnow = datetime.utcnow()
    today = convert_utc_to_bst(utcnow)
    last_2_days = utcnow - timedelta(days=2)
    last_bst_date_for_ft = convert_utc_to_bst(last_2_days)
    # if year end date is less than today, we are calculating for data in the past and have no need for deltas.
    if year_end_date >= today:
        todays_data = get_deltas(service_id, last_2_days, today)
        year_end_date = last_bst_date_for_ft


    yearly_data = db.session.query(
        FactBilling.notifications_sent,
        FactBilling.billable_units,
        FactBilling.service_id,
        FactBilling.notification_type,
        FactBilling.rate,
        FactBilling.rate_multiplier,
        FactBilling.international
    ).filter(
        FactBilling.service_id == service_id,
        FactBilling.bst_date >= year_start_date,
        FactBilling.bst_date <= last_bst_date_for_ft
    ).all()

    # today_data + yearly_data and aggregate by month


def get_deltas(service_id, start_date_end_date):
    # query ft_billing data using queries from create_nightly_billing
    return []


