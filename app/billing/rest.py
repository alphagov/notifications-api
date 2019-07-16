from flask import Blueprint, jsonify, request

from app.billing.billing_schemas import (
    create_or_update_free_sms_fragment_limit_schema,
    serialize_ft_billing_remove_emails,
    serialize_ft_billing_yearly_totals,
)
from app.dao.annual_billing_dao import (
    dao_get_free_sms_fragment_limit_for_year,
    dao_get_all_free_sms_fragment_limit,
    dao_create_or_update_annual_billing_for_year,
    dao_update_annual_billing_for_future_years
)
from app.dao.date_util import get_current_financial_year_start_year
from app.dao.fact_billing_dao import fetch_monthly_billing_for_year, fetch_billing_totals_for_year

from app.errors import InvalidRequest
from app.errors import register_errors
from app.schema_validation import validate

billing_blueprint = Blueprint(
    'billing',
    __name__,
    url_prefix='/service/<uuid:service_id>/billing'
)


register_errors(billing_blueprint)


@billing_blueprint.route('/ft-monthly-usage')
@billing_blueprint.route('/monthly-usage')
def get_yearly_usage_by_monthly_from_ft_billing(service_id):
    try:
        year = int(request.args.get('year'))
    except TypeError:
        return jsonify(result='error', message='No valid year provided'), 400
    results = fetch_monthly_billing_for_year(service_id=service_id, year=year)
    data = serialize_ft_billing_remove_emails(results)
    return jsonify(data)


@billing_blueprint.route('/ft-yearly-usage-summary')
@billing_blueprint.route('/yearly-usage-summary')
def get_yearly_billing_usage_summary_from_ft_billing(service_id):
    try:
        year = int(request.args.get('year'))
    except TypeError:
        return jsonify(result='error', message='No valid year provided'), 400

    billing_data = fetch_billing_totals_for_year(service_id, year)
    data = serialize_ft_billing_yearly_totals(billing_data)
    return jsonify(data)


@billing_blueprint.route('/free-sms-fragment-limit', methods=["GET"])
def get_free_sms_fragment_limit(service_id):

    financial_year_start = request.args.get('financial_year_start')

    annual_billing = get_or_create_free_sms_fragment_limit(financial_year_start, service_id)

    return jsonify(annual_billing.serialize_free_sms_items()), 200


def get_or_create_free_sms_fragment_limit(financial_year_start, service_id):
    annual_billing = dao_get_free_sms_fragment_limit_for_year(service_id, financial_year_start)
    if annual_billing is None:
        # An entry does not exist in annual_billing table for that service and year. If it is a past year,
        # we return the oldest entry.
        # If it is the current or future years, we create an entry in the db table using the newest record,
        # and return that number.  If all fails, we return InvalidRequest.
        sms_list = dao_get_all_free_sms_fragment_limit(service_id)

        if not sms_list:
            raise InvalidRequest('no free-sms-fragment-limit entry for service {} in DB'.format(service_id), 404)
        else:
            if financial_year_start is None:
                financial_year_start = get_current_financial_year_start_year()

            if int(financial_year_start) < get_current_financial_year_start_year():
                # return the earliest historical entry
                annual_billing = sms_list[0]  # The oldest entry
            else:
                annual_billing = sms_list[-1]  # The newest entry

                annual_billing = dao_create_or_update_annual_billing_for_year(service_id,
                                                                              annual_billing.free_sms_fragment_limit,
                                                                              financial_year_start)
    return annual_billing


@billing_blueprint.route('/free-sms-fragment-limit', methods=["POST"])
def create_or_update_free_sms_fragment_limit(service_id):

    req_args = request.get_json()

    form = validate(req_args, create_or_update_free_sms_fragment_limit_schema)

    update_free_sms_fragment_limit_data(service_id,
                                        free_sms_fragment_limit=form.get('free_sms_fragment_limit'),
                                        financial_year_start=form.get('financial_year_start'))
    return jsonify(form), 201


def update_free_sms_fragment_limit_data(service_id, free_sms_fragment_limit, financial_year_start):
    current_year = get_current_financial_year_start_year()
    if not financial_year_start:
        financial_year_start = current_year

    dao_create_or_update_annual_billing_for_year(
        service_id,
        free_sms_fragment_limit,
        financial_year_start
    )
    # if we're trying to update historical data, don't touch other rows.
    # Otherwise, make sure that future years will get the new updated value.
    if financial_year_start >= current_year:
        dao_update_annual_billing_for_future_years(
            service_id,
            free_sms_fragment_limit,
            financial_year_start
        )
