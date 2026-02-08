from datetime import datetime

from flask import Blueprint, jsonify, request

from app import db
from app.constants import UK_POSTAGE_TYPES
from app.dao.date_util import get_financial_year_for_datetime
from app.dao.fact_billing_dao import (
    fetch_daily_sms_provider_volumes_for_platform,
    fetch_daily_volumes_for_platform,
    fetch_dvla_billing_facts,
    fetch_usage_for_all_services_letter,
    fetch_usage_for_all_services_letter_breakdown,
    fetch_usage_for_all_services_sms,
    fetch_volumes_by_service,
)
from app.dao.fact_notification_status_dao import (
    fetch_notification_status_totals_for_all_services,
)
from app.dao.services_dao import fetch_billing_details_for_all_services
from app.errors import InvalidRequest, register_errors
from app.platform_stats.platform_stats_schema import platform_stats_request
from app.schema_validation import validate
from app.service.statistics import format_admin_stats
from app.utils import get_london_midnight_in_utc

platform_stats_blueprint = Blueprint("platform_stats", __name__)

register_errors(platform_stats_blueprint)


@platform_stats_blueprint.route("")
def get_platform_stats():
    if request.args:
        validate(request.args, platform_stats_request)

    # If start and end date are not set, we are expecting today's stats.
    today = str(datetime.utcnow().date())

    start_date = datetime.strptime(request.args.get("start_date", today), "%Y-%m-%d").date()
    end_date = datetime.strptime(request.args.get("end_date", today), "%Y-%m-%d").date()
    data = fetch_notification_status_totals_for_all_services(start_date=start_date, end_date=end_date)
    stats = format_admin_stats(data)

    return jsonify(stats)


def validate_date_format(date_to_validate):
    try:
        validated_date = datetime.strptime(date_to_validate, "%Y-%m-%d").date()
    except ValueError as e:
        raise InvalidRequest(message="Input must be a date in the format: YYYY-MM-DD", status_code=400) from e
    return validated_date


def validate_date_range_is_within_a_financial_year(start_date, end_date):
    start_date = validate_date_format(start_date)
    end_date = validate_date_format(end_date)
    if end_date < start_date:
        raise InvalidRequest(message="Start date must be before end date", status_code=400)

    start_fy = get_financial_year_for_datetime(get_london_midnight_in_utc(start_date))
    end_fy = get_financial_year_for_datetime(get_london_midnight_in_utc(end_date))

    if start_fy != end_fy:
        raise InvalidRequest(message="Date must be in a single financial year.", status_code=400)

    return start_date, end_date


@platform_stats_blueprint.route("data-for-billing-report")
def get_data_for_billing_report():
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    start_date, end_date = validate_date_range_is_within_a_financial_year(start_date, end_date)

    sms_costs = fetch_usage_for_all_services_sms(
        start_date,
        end_date,
        session=db.session_bulk,
        retry_attempts=2,  # type: ignore[call-arg]
    )
    letter_overview = fetch_usage_for_all_services_letter(
        start_date, end_date, session=db.session_bulk, retry_attempts=2
    )
    letter_breakdown = fetch_usage_for_all_services_letter_breakdown(
        start_date, end_date, session=db.session_bulk, retry_attempts=2
    )

    lb_by_service = [
        (
            lb.service_id,
            f"{lb.letters_sent} {postage_description(lb.postage)} letters at {format_letter_rate(lb.letter_rate)}",
        )
        for lb in letter_breakdown
    ]
    combined = {}
    for s in sms_costs:
        if float(s.cost) > 0:
            entry = {
                "organisation_id": str(s.organisation_id) if s.organisation_id else "",
                "organisation_name": s.organisation_name or "",
                "service_id": str(s.service_id),
                "service_name": s.service_name,
                "sms_cost": float(s.cost),
                "sms_chargeable_units": s.charged_units,
                "total_letters": 0,
                "letter_cost": 0,
                "letter_breakdown": "",
            }
            combined[s.service_id] = entry

    for data in letter_overview:
        if data.service_id in combined:
            combined[data.service_id].update(
                {"total_letters": data.total_letters, "letter_cost": float(data.letter_cost)}
            )

        else:
            letter_entry = {
                "organisation_id": str(data.organisation_id) if data.organisation_id else "",
                "organisation_name": data.organisation_name or "",
                "service_id": str(data.service_id),
                "service_name": data.service_name,
                "sms_cost": 0,
                "sms_chargeable_units": 0,
                "total_letters": data.total_letters,
                "letter_cost": float(data.letter_cost),
                "letter_breakdown": "",
            }
            combined[data.service_id] = letter_entry
    for service_id, breakdown in lb_by_service:
        combined[service_id]["letter_breakdown"] += breakdown + "\n"

    billing_details = fetch_billing_details_for_all_services(session=db.session_bulk, retry_attempts=2)
    for service in billing_details:
        if service.service_id in combined:
            combined[service.service_id].update(
                {
                    "purchase_order_number": service.purchase_order_number,
                    "contact_names": service.billing_contact_names,
                    "contact_email_addresses": service.billing_contact_email_addresses,
                    "billing_reference": service.billing_reference,
                }
            )

    # sorting first by name == '' means that blank orgs will be sorted last.

    result = sorted(
        combined.values(), key=lambda x: (x["organisation_name"] == "", x["organisation_name"], x["service_name"])
    )
    return jsonify(result)


@platform_stats_blueprint.route("data-for-dvla-billing-report")
def get_data_for_dvla_billing_report():
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    start_date, end_date = validate_date_range_is_within_a_financial_year(start_date, end_date)

    billing_facts = fetch_dvla_billing_facts(start_date, end_date, session=db.session_bulk, retry_attempts=2)

    return jsonify(
        [
            {
                "date": fact.date.isoformat(),
                "postage": fact.postage,
                "cost_threshold": fact.cost_threshold.value,
                "sheets": fact.sheets,
                "rate": float(fact.rate),
                "letters": fact.letters,
                "cost": float(fact.cost),
            }
            for fact in billing_facts
        ]
    )


@platform_stats_blueprint.route("daily-volumes-report")
def daily_volumes_report():
    start_date = validate_date_format(request.args.get("start_date"))
    end_date = validate_date_format(request.args.get("end_date"))

    daily_volumes = fetch_daily_volumes_for_platform(start_date, end_date)
    report = []

    for row in daily_volumes:
        report.append(
            {
                "day": row.bst_date,
                "sms_totals": int(row.sms_totals),
                "sms_fragment_totals": int(row.sms_fragment_totals),
                "sms_chargeable_units": int(row.sms_chargeable_units),
                "email_totals": int(row.email_totals),
                "letter_totals": int(row.letter_totals),
                "letter_sheet_totals": int(row.letter_sheet_totals),
            }
        )
    return jsonify(report)


@platform_stats_blueprint.route("daily-sms-provider-volumes-report")
def daily_sms_provider_volumes_report():
    start_date = validate_date_format(request.args.get("start_date"))
    end_date = validate_date_format(request.args.get("end_date"))

    daily_volumes = fetch_daily_sms_provider_volumes_for_platform(
        start_date, end_date, session=db.session_bulk, retry_attempts=2
    )
    report = []

    for row in daily_volumes:
        report.append(
            {
                "day": row.bst_date.isoformat(),
                "provider": row.provider,
                "sms_totals": int(row.sms_totals),
                "sms_fragment_totals": int(row.sms_fragment_totals),
                "sms_chargeable_units": int(row.sms_chargeable_units),
                # convert from Decimal to float as it's not json serialisable
                "sms_cost": float(row.sms_cost),
            }
        )
    return jsonify(report)


@platform_stats_blueprint.route("volumes-by-service")
def volumes_by_service_report():
    start_date = validate_date_format(request.args.get("start_date"))
    end_date = validate_date_format(request.args.get("end_date"))

    volumes_by_service = fetch_volumes_by_service(start_date, end_date, session=db.session_bulk, retry_attempts=2)
    report = []

    for row in volumes_by_service:
        report.append(
            {
                "service_name": row.service_name,
                "service_id": str(row.service_id),
                "organisation_name": row.organisation_name if row.organisation_name else "",
                "organisation_id": str(row.organisation_id) if row.organisation_id else "",
                "free_allowance": int(row.free_allowance),
                "sms_notifications": int(row.sms_notifications),
                "sms_chargeable_units": int(row.sms_chargeable_units),
                "email_totals": int(row.email_totals),
                "letter_totals": int(row.letter_totals),
                "letter_sheet_totals": int(row.letter_sheet_totals),
                "letter_cost": float(row.letter_cost),
            }
        )

    return jsonify(report)


def postage_description(postage):
    if postage in UK_POSTAGE_TYPES:
        return f"{postage} class"
    else:
        return "international"


def format_letter_rate(number):
    if number >= 1:
        return f"£{number:,.2f}"

    return f"{number * 100:.0f}p"
