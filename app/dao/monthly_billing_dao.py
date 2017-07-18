from datetime import datetime

from app import db
from app.dao.notification_usage_dao import get_billing_data_for_month
from app.models import MonthlyBilling, SMS_TYPE


def create_or_update_monthly_billing_sms(service_id, billing_month):
    monthly = get_billing_data_for_month(service_id=service_id, billing_month=billing_month)
    # update monthly
    monthly_totals = _monthly_billing_data_to_json(monthly)
    row = MonthlyBilling.query.filter_by(year=billing_month.year,
                                         month=datetime.strftime(billing_month, "%B"),
                                         notification_type='sms').first()
    if row:
        row.monthly_totals = monthly_totals
    else:
        row = MonthlyBilling(service_id=service_id,
                             notification_type=SMS_TYPE,
                             year=billing_month.year,
                             month=datetime.strftime(billing_month, "%B"),
                             monthly_totals=monthly_totals)
    db.session.add(row)
    db.session.commit()


def get_monthly_billing_sms(service_id, billing_month):
    monthly = MonthlyBilling.query.filter_by(service_id=service_id,
                                             year=billing_month.year,
                                             month=datetime.strftime(billing_month, "%B"),
                                             notification_type=SMS_TYPE).first()
    return monthly


def _monthly_billing_data_to_json(monthly):
    # ('April', 6, 1, False, 'sms', 0.014)
    #  (month, billing_units, rate_multiplier, international, notification_type, rate)
    # total cost must take into account the free allowance.
    # might be a good idea to capture free allowance in this table
    return [{"billing_units": x[1],
             "rate_multiplier": x[2],
             "international": x[3],
             "rate": x[5],
             "total_cost": (x[1] * x[2]) * x[5]} for x in monthly]
