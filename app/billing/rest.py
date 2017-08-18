from datetime import datetime
import json

from flask import Blueprint, jsonify, request

from app.dao.monthly_billing_dao import (
    get_billing_data_for_financial_year,
    get_monthly_billing_by_notification_type
)
from app.dao.date_util import get_financial_year, get_months_for_financial_year
from app.errors import register_errors
from app.models import SMS_TYPE, EMAIL_TYPE
from app.utils import convert_utc_to_bst

billing_blueprint = Blueprint(
    'billing',
    __name__,
    url_prefix='/service/<uuid:service_id>/billing'
)


register_errors(billing_blueprint)


@billing_blueprint.route('/monthly-usage')
def get_yearly_usage_by_month(service_id):
    try:
        year = int(request.args.get('year'))
        start_date, end_date = get_financial_year(year)
        results = []
        for month in get_months_for_financial_year(year):
            billing_for_month = get_monthly_billing_by_notification_type(service_id, month, SMS_TYPE)
            if billing_for_month:
                results.append(_transform_billing_for_month(billing_for_month))
        return json.dumps(results)

    except TypeError:
        return jsonify(result='error', message='No valid year provided'), 400


@billing_blueprint.route('/yearly-usage-summary')
def get_yearly_billing_usage_summary(service_id):
    try:
        year = int(request.args.get('year'))
        billing_data = get_billing_data_for_financial_year(service_id, year)
        notification_types = [SMS_TYPE, EMAIL_TYPE]
        response = [
            _get_total_billable_units_and_rate_for_notification_type(billing_data, notification_type)
            for notification_type in notification_types
        ]

        return json.dumps(response)

    except TypeError:
        return jsonify(result='error', message='No valid year provided'), 400


def _get_total_billable_units_and_rate_for_notification_type(billing_data, noti_type):
    total_sent = 0
    rate = 0
    for entry in billing_data:
        for monthly_total in entry.monthly_totals:
            if entry.notification_type == noti_type:
                total_sent += monthly_total['billing_units'] \
                    if noti_type == EMAIL_TYPE else (monthly_total['billing_units'] * monthly_total['rate_multiplier'])
                rate = monthly_total['rate']

    return {
        "notification_type": noti_type,
        "billing_units": total_sent,
        "rate": rate
    }


def _transform_billing_for_month(billing_for_month):
    month_name = datetime.strftime(convert_utc_to_bst(billing_for_month.start_date), "%B")
    billing_units = rate = rate_multiplier = international = 0

    if billing_for_month.monthly_totals:
        billing_units = billing_for_month.monthly_totals[0]['billing_units']
        rate = billing_for_month.monthly_totals[0]['rate']
        rate_multiplier = billing_for_month.monthly_totals[0]['rate_multiplier']
        international = billing_for_month.monthly_totals[0]['international']

    return {
        "month": month_name,
        "billing_units": billing_units,
        "rate_multiplier": rate_multiplier,
        "international": bool(international),
        "notification_type": billing_for_month.notification_type,
        "rate": rate
    }
