from flask import current_app
from sqlalchemy import desc

from app import db
from app.constants import ORG_TYPE_OTHER, SMS_TYPE
from app.dao.dao_utils import autocommit
from app.dao.date_util import get_current_financial_year_start_year
from app.models import AnnualBilling, DefaultAnnualAllowance


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


def dao_get_free_sms_fragment_limit_for_year(service_id, financial_year_start=None):
    if not financial_year_start:
        financial_year_start = get_current_financial_year_start_year()

    return AnnualBilling.query.filter_by(service_id=service_id, financial_year_start=financial_year_start).first()


def set_default_free_allowance_for_service(service, year_start=None):
    current_financial_year_start = get_current_financial_year_start_year()
    if not year_start:
        year_start = current_financial_year_start

    # Notify came into existence in 2016, so we don't have allowances before then. If someone's querying for an earlier
    # year, or a year after the current one, they're probably URL hacking: we shouldn't continue. Inserting
    # AnnualBilling entries for those years doesn't make sense.
    if year_start < 2016:
        raise ValueError("year_start before 2016 is invalid")
    elif year_start > current_financial_year_start:
        raise ValueError("year_start cannot be in a future financial year")

    if not (org_type := service.organisation_type):
        current_app.logger.warning(
            "No organisation type for service %s. Using default for `other` org type.", service.id
        )
        org_type = ORG_TYPE_OTHER

    # If the service had 0 allowance for the previous year, let's pull that forward.
    if (
        AnnualBilling.query.filter_by(
            service_id=service.id, financial_year_start=year_start - 1, free_sms_fragment_limit=0
        ).count()
        == 1
    ):
        free_sms_fragment_allowance = 0

    else:
        # Find the default annual allowance for the service's org type with the most recent
        # valid_from_financial_year_start.
        default_free_sms_fragment_allowance = (
            DefaultAnnualAllowance.query.filter(
                DefaultAnnualAllowance.valid_from_financial_year_start <= year_start,
                DefaultAnnualAllowance.organisation_type == org_type,
                DefaultAnnualAllowance.notification_type == SMS_TYPE,
            )
            .order_by(desc(DefaultAnnualAllowance.valid_from_financial_year_start))
            .first()
        )
        if not default_free_sms_fragment_allowance:
            raise RuntimeError(
                f"No default annual allowance for {org_type=} with valid_from_financial_year_start<={year_start}"
            )
        free_sms_fragment_allowance = default_free_sms_fragment_allowance.allowance

    current_app.logger.info(
        (
            "Set default free allowances for service %s "
            "(valid_from_financial_year_start=%s, free_sms_fragment_allowance=%s)"
        ),
        service.id,
        year_start,
        free_sms_fragment_allowance,
    )
    return dao_create_or_update_annual_billing_for_year(service.id, free_sms_fragment_allowance, year_start)
