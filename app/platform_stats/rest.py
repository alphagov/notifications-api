from datetime import datetime

from flask import Blueprint, jsonify, request

from app.dao.date_util import get_financial_year
from app.dao.fact_billing_dao import (
    fetch_sms_billing_for_all_services, fetch_letter_costs_for_all_services,
    fetch_letter_line_items_for_all_services
)
from app.dao.fact_notification_status_dao import fetch_notification_status_totals_for_all_services
from app.errors import register_errors, InvalidRequest
from app.platform_stats.platform_stats_schema import platform_stats_request
from app.service.statistics import format_admin_stats
from app.schema_validation import validate

platform_stats_blueprint = Blueprint('platform_stats', __name__)

register_errors(platform_stats_blueprint)


@platform_stats_blueprint.route('')
def get_platform_stats():
    if request.args:
        validate(request.args, platform_stats_request)

    # If start and end date are not set, we are expecting today's stats.
    today = str(datetime.utcnow().date())

    start_date = datetime.strptime(request.args.get('start_date', today), '%Y-%m-%d').date()
    end_date = datetime.strptime(request.args.get('end_date', today), '%Y-%m-%d').date()
    data = fetch_notification_status_totals_for_all_services(start_date=start_date, end_date=end_date)
    stats = format_admin_stats(data)

    return jsonify(stats)


def validate_date_range_is_within_a_financial_year(start_date, end_date):
    try:
        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        raise InvalidRequest(message="Input must be a date in the format: YYYY-MM-DD", status_code=400)
    if end_date < start_date:
        raise InvalidRequest(message="Start date must be before end date", status_code=400)
    if 4 <= int(start_date.strftime("%m")) <= 12:
        year_start, year_end = get_financial_year(year=int(start_date.strftime("%Y")))
    else:
        year_start, year_end = get_financial_year(year=int(start_date.strftime("%Y")) - 1)
    year_start = year_start.date()
    year_end = year_end.date()
    if year_start <= start_date <= year_end and year_start <= end_date <= year_end:
        return True
    else:
        raise InvalidRequest(message="Date must be in a single financial year.", status_code=400)


@platform_stats_blueprint.route('usage-for-all-services')
def get_usage_for_all_services():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    validate_date_range_is_within_a_financial_year(start_date, end_date)
    start_date = datetime.strptime(start_date, "%Y-%m-%d")
    end_date = datetime.strptime(end_date, "%Y-%m-%d")

    sms_costs = fetch_sms_billing_for_all_services(start_date, end_date)
    letter_costs = fetch_letter_costs_for_all_services(start_date, end_date)
    letter_breakdown = fetch_letter_line_items_for_all_services(start_date, end_date)

    lb_by_service = [(lb.service_id, "{} {} class letters at {}p".format(lb.letters_sent, lb.postage, lb.letter_rate))
                     for lb in letter_breakdown]
    combined = {}
    for s in sms_costs:
        entry = {
            "Organisation_id": str(s.organisation_id) if s.organisation_id else "",
            "Organisation_name": s.organisation_name or "",
            "service_id": str(s.service_id),
            "service_name": s.service_name,
            "sms_cost": str(s.sms_cost),
            "letter_cost": 0,
            "letter_breakdown": ""
        }
        combined[str(s.service_id)] = entry

    for l in letter_costs:
        if l.service_id in combined:
            combined[str(l.service_id)].update({'letter_cost': l.letter_cost})
        else:
            letter_entry = {
                "Organisation_id": str(l.organisation_id) if l.organisation_id else "",
                "Organisation_name": l.organisation_name or "",
                "service_id": str(l.service_id),
                "service_name": l.service_name,
                "sms_cost": 0,
                "letter_cost": str(l.letter_cost),
                "letter_breakdown": ""
            }
            combined[str(l.service_id)] = letter_entry
    for service_id, breakdown in lb_by_service:
        combined[str(service_id)]['letter_breakdown'] += (breakdown + '\n')

    return jsonify(list(combined.values()))
