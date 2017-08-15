from datetime import datetime
import json

from flask import Blueprint, jsonify, request

from app.dao.notification_usage_dao import get_billing_data_for_month
from app.dao.monthly_billing_dao import get_billing_data_for_financial_year
from app.dao.date_util import get_financial_year
from app.errors import register_errors
from app.models import SMS_TYPE, EMAIL_TYPE


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
        results = get_billing_data_for_month(service_id, start_date, end_date, SMS_TYPE)
        json_results = [{
            "month": datetime.strftime(x[0], "%B"),
            "billing_units": x[1],
            "rate_multiplier": x[2],
            "international": x[3],
            "notification_type": x[4],
            "rate": x[5]
        } for x in results]
        return json.dumps(json_results)
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
