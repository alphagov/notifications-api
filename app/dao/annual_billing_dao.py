from flask import current_app

from app import db
from app.dao.dao_utils import transactional
from app.dao.date_util import get_current_financial_year_start_year
from app.models import AnnualBilling


@transactional
def dao_create_or_update_annual_billing_for_year(service_id, free_sms_fragment_limit, financial_year_start):
    result = dao_get_free_sms_fragment_limit_for_year(service_id, financial_year_start)

    if result:
        result.free_sms_fragment_limit = free_sms_fragment_limit
    else:
        result = AnnualBilling(service_id=service_id, financial_year_start=financial_year_start,
                               free_sms_fragment_limit=free_sms_fragment_limit)
    db.session.add(result)
    return result


def dao_get_annual_billing(service_id):
    return AnnualBilling.query.filter_by(
        service_id=service_id,
    ).order_by(AnnualBilling.financial_year_start).all()


@transactional
def dao_update_annual_billing_for_future_years(service_id, free_sms_fragment_limit, financial_year_start):
    AnnualBilling.query.filter(
        AnnualBilling.service_id == service_id,
        AnnualBilling.financial_year_start > financial_year_start
    ).update(
        {'free_sms_fragment_limit': free_sms_fragment_limit}
    )


def dao_get_free_sms_fragment_limit_for_year(service_id, financial_year_start=None):

    if not financial_year_start:
        financial_year_start = get_current_financial_year_start_year()

    return AnnualBilling.query.filter_by(
        service_id=service_id,
        financial_year_start=financial_year_start
    ).first()


def dao_get_all_free_sms_fragment_limit(service_id):

    return AnnualBilling.query.filter_by(
        service_id=service_id,
    ).order_by(AnnualBilling.financial_year_start).all()


def set_default_free_allowance_for_service(service, year_start=None):
    default_free_sms_fragment_limits = {
        'central': {
            2020: 250_000,
            2021: 150_000,
        },
        'local': {
            2020: 25_000,
            2021: 25_000,
        },
        'nhs_central': {
            2020: 250_000,
            2021: 150_000,
        },
        'nhs_local': {
            2020: 25_000,
            2021: 25_000,
        },
        'nhs_gp': {
            2020: 25_000,
            2021: 10_000,
        },
        'emergency_service': {
            2020: 25_000,
            2021: 25_000,
        },
        'school_or_college': {
            2020: 25_000,
            2021: 10_000,
        },
        'other': {
            2020: 25_000,
            2021: 10_000,
        },
    }
    if not year_start:
        year_start = get_current_financial_year_start_year()
    if service.organisation_type:
        free_allowance = default_free_sms_fragment_limits[service.organisation_type][year_start]
    else:
        current_app.logger.info(f"no organisation type for service {service.id}. Using other default of "
                                f"{default_free_sms_fragment_limits['other'][year_start]}")
        free_allowance = default_free_sms_fragment_limits['other'][year_start]

    dao_create_or_update_annual_billing_for_year(
        service.id,
        free_allowance,
        year_start
    )
