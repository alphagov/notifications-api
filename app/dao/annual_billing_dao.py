from flask import current_app

from app import db
from app.dao.dao_utils import autocommit
from app.dao.date_util import get_current_financial_year_start_year
from app.models import AnnualBilling


@autocommit
def dao_create_or_update_annual_billing_for_year(service_id, free_sms_fragment_limit, financial_year_start):
    result = dao_get_free_sms_fragment_limit_for_year(service_id, financial_year_start)

    if result:
        result.free_sms_fragment_limit = free_sms_fragment_limit
    else:
        result = AnnualBilling(
            service_id=service_id,
            financial_year_start=financial_year_start,
            free_sms_fragment_limit=free_sms_fragment_limit,
        )
    db.session.add(result)
    return result


@autocommit
def dao_update_annual_billing_for_future_years(service_id, free_sms_fragment_limit, financial_year_start):
    AnnualBilling.query.filter(
        AnnualBilling.service_id == service_id, AnnualBilling.financial_year_start > financial_year_start
    ).update({"free_sms_fragment_limit": free_sms_fragment_limit})


def dao_get_free_sms_fragment_limit_for_year(service_id, financial_year_start=None):

    if not financial_year_start:
        financial_year_start = get_current_financial_year_start_year()

    return AnnualBilling.query.filter_by(service_id=service_id, financial_year_start=financial_year_start).first()


def set_default_free_allowance_for_service(service, year_start=None):
    default_free_sms_fragment_limits = {
        "central": {
            2020: 250_000,
            2021: 150_000,
            2022: 40_000,
            2023: 40_000,
        },
        "local": {
            2020: 25_000,
            2021: 25_000,
            2022: 20_000,
            2023: 20_000,
        },
        "nhs_central": {
            2020: 250_000,
            2021: 150_000,
            2022: 40_000,
            2023: 40_000,
        },
        "nhs_local": {
            2020: 25_000,
            2021: 25_000,
            2022: 20_000,
            2023: 20_000,
        },
        "nhs_gp": {
            2020: 25_000,
            2021: 10_000,
            2022: 10_000,
            2023: 10_000,
        },
        "emergency_service": {
            2020: 25_000,
            2021: 25_000,
            2022: 20_000,
            2023: 20_000,
        },
        "school_or_college": {
            2020: 25_000,
            2021: 10_000,
            2022: 10_000,
            2023: 10_000,
        },
        "other": {
            2020: 25_000,
            2021: 10_000,
            2022: 10_000,
            2023: 10_000,
        },
    }
    if not year_start:
        year_start = get_current_financial_year_start_year()

    use_allowance_from = year_start

    if year_start < 2020:
        use_allowance_from = 2020
    elif year_start > 2023:
        current_app.logger.error(
            f"Annual allowances have not been updated for the current year ({year_start}). Using 2023 allowances."
        )
        use_allowance_from = 2023

    if service.organisation_type:
        free_allowance = default_free_sms_fragment_limits[service.organisation_type][use_allowance_from]

    else:
        current_app.logger.error(
            f"no organisation type for service {service.id}. Using other default of "
            f"{default_free_sms_fragment_limits['other'][use_allowance_from]}"
        )
        free_allowance = default_free_sms_fragment_limits["other"][use_allowance_from]

    return dao_create_or_update_annual_billing_for_year(service.id, free_allowance, year_start)
