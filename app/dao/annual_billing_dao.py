from app import db
from app.dao.dao_utils import (
    transactional,
)
from app.models import AnnualBilling
from app.dao.date_util import get_current_financial_year_start_year


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
def dao_update_annual_billing_for_current_and_future_years(service_id, free_sms_fragment_limit, financial_year_start):
    AnnualBilling.query.filter(
        AnnualBilling.service_id == service_id,
        AnnualBilling.financial_year_start >= financial_year_start
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


def dao_insert_annual_billing_for_this_year(service, free_sms_fragment_limit):
    """
    This method is called from create_service which is wrapped in a transaction.
    """
    annual_billing = AnnualBilling(
        free_sms_fragment_limit=free_sms_fragment_limit,
        financial_year_start=get_current_financial_year_start_year(),
        service=service,
    )

    db.session.add(annual_billing)
