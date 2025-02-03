from flask import Blueprint, abort, jsonify, request

from app.billing.billing_schemas import (
    create_or_update_free_sms_fragment_limit_schema,
    serialize_ft_billing_remove_emails,
    serialize_ft_billing_yearly_totals,
)
from app.dao.annual_billing_dao import (
    dao_create_or_update_annual_billing_for_year,
    dao_get_default_annual_allowance_for_service,
    dao_get_free_sms_fragment_limit_for_year,
    set_default_free_allowance_for_service,
)
from app.dao.date_util import get_current_financial_year_start_year
from app.dao.fact_billing_dao import (
    fetch_usage_for_service_annual,
    fetch_usage_for_service_by_month,
)
from app.dao.services_dao import dao_fetch_service_by_id
from app.errors import register_errors
from app.models import Service
from app.schema_validation import validate

billing_blueprint = Blueprint("billing", __name__, url_prefix="/service/<uuid:service_id>/billing")


register_errors(billing_blueprint)


@billing_blueprint.route("/monthly-usage")
def get_yearly_usage_by_monthly_from_ft_billing(service_id):
    try:
        year = int(request.args.get("year"))
    except TypeError:
        return jsonify(result="error", message="No valid year provided"), 400
    results = fetch_usage_for_service_by_month(service_id=service_id, year=year)
    data = serialize_ft_billing_remove_emails(results)
    return jsonify(data)


@billing_blueprint.route("/yearly-usage-summary")
def get_yearly_billing_usage_summary_from_ft_billing(service_id):
    try:
        year = int(request.args.get("year"))
    except TypeError:
        return jsonify(result="error", message="No valid year provided"), 400

    billing_data = fetch_usage_for_service_annual(service_id, year)
    data = serialize_ft_billing_yearly_totals(billing_data)
    return jsonify(data)


@billing_blueprint.route("/free-sms-fragment-limit", methods=["GET"])
def get_free_sms_fragment_limit(service_id):
    financial_year_start = request.args.get("financial_year_start")

    annual_billing = dao_get_free_sms_fragment_limit_for_year(service_id, financial_year_start)

    if annual_billing is None:
        service = Service.query.get(service_id)
        # An entry does not exist in annual_billing table for that service and year.
        # Set the annual billing to the default free allowance based on the organisation type of the service.

        try:
            annual_billing = set_default_free_allowance_for_service(
                service=service, year_start=int(financial_year_start) if financial_year_start else None
            )
        except ValueError:
            abort(400)

    return jsonify(annual_billing.serialize_free_sms_items()), 200


@billing_blueprint.route("/free-sms-fragment-limit", methods=["POST"])
def create_or_update_free_sms_fragment_limit(service_id):
    req_args = request.get_json()

    form = validate(req_args, create_or_update_free_sms_fragment_limit_schema)

    update_free_sms_fragment_limit_data(
        service_id,
        free_sms_fragment_limit=form.get("free_sms_fragment_limit"),
    )
    return jsonify(form), 201


def update_free_sms_fragment_limit_data(service_id, free_sms_fragment_limit):
    """
    Update the free allowance for a service for this year.

    If updating the free allowance now means that a service has the default allowance for its
    org type, we set `has_custom_allowance` to False, otherwise it is True.
    """
    current_year = get_current_financial_year_start_year()
    service = dao_fetch_service_by_id(service_id, with_users=False)
    default_free_allowance = dao_get_default_annual_allowance_for_service(service, current_year)

    dao_create_or_update_annual_billing_for_year(
        service_id,
        free_sms_fragment_limit,
        current_year,
        has_custom_allowance=default_free_allowance != free_sms_fragment_limit,
    )
