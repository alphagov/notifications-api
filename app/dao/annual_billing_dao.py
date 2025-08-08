from flask import current_app
from sqlalchemy import desc

from app import db
from app.constants import HIGH_VOLUME_SERVICE_THRESHOLD, ORG_TYPE_OTHER, SMS_TYPE
from app.dao.dao_utils import autocommit
from app.dao.date_util import get_current_financial_year_start_year
from app.dao.fact_billing_dao import get_sms_fragments_sent_last_financial_year
from app.models import AnnualBilling, DefaultAnnualAllowance


@autocommit
def dao_create_or_update_annual_billing_for_year(
    service_id,
    free_sms_fragment_limit,
    financial_year_start,
    high_volume_service_last_year=None,
    has_custom_allowance=None,
):
    result = dao_get_free_sms_fragment_limit_for_year(service_id, financial_year_start)

    if result:
        result.free_sms_fragment_limit = free_sms_fragment_limit
    else:
        result = AnnualBilling(
            service_id=service_id,
            financial_year_start=financial_year_start,
            free_sms_fragment_limit=free_sms_fragment_limit,
        )

    if high_volume_service_last_year is not None:
        result.high_volume_service_last_year = high_volume_service_last_year

    if has_custom_allowance is not None:
        result.has_custom_allowance = has_custom_allowance

    db.session.add(result)
    return result


def dao_get_free_sms_fragment_limit_for_year(service_id, financial_year_start=None):
    if not financial_year_start:
        financial_year_start = get_current_financial_year_start_year()

    return AnnualBilling.query.filter_by(service_id=service_id, financial_year_start=financial_year_start).first()


def dao_get_default_annual_allowance_for_service(service, year_start):
    if not (org_type := service.organisation_type):
        current_app.logger.warning(
            "No organisation type for service %s. Using default for `other` org type.", service.id
        )
        org_type = ORG_TYPE_OTHER

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

    return default_free_sms_fragment_allowance


def set_default_free_allowance_for_service(service, year_start=None, _autocommit=True):
    current_financial_year_start = get_current_financial_year_start_year()
    if not year_start:
        year_start = current_financial_year_start
    raise Exception("Rollback error")
    # Notify came into existence in 2016, so we don't have allowances before then. If someone's querying for an earlier
    # year, or a year after the current one, they're probably URL hacking: we shouldn't continue. Inserting
    # AnnualBilling entries for those years doesn't make sense.
    if year_start < 2016:
        raise ValueError("year_start before 2016 is invalid")
    elif year_start > current_financial_year_start:
        raise ValueError("year_start cannot be in a future financial year")

    if _is_high_volume_service(service):
        next_free_sms_fragment_allowance = 0
        high_volume_service_last_year = True
        has_custom_allowance = False

    else:
        high_volume_service_last_year = False

        # get last year's row if it exists
        last_years_allowance = AnnualBilling.query.filter_by(
            service_id=service.id,
            financial_year_start=year_start - 1,
        ).first()

        if last_years_allowance and last_years_allowance.has_custom_allowance:
            # carry over the allowance from last year
            next_free_sms_fragment_allowance = last_years_allowance.free_sms_fragment_limit
            has_custom_allowance = True
        else:
            # get the default for the org
            default_free_sms_fragment_allowance = dao_get_default_annual_allowance_for_service(service, year_start)
            next_free_sms_fragment_allowance = default_free_sms_fragment_allowance.allowance
            has_custom_allowance = False

    current_app.logger.info(
        (
            "Set default free allowances for service %s "
            "(valid_from_financial_year_start=%s, free_sms_fragment_allowance=%s)"
        ),
        service.id,
        year_start,
        next_free_sms_fragment_allowance,
    )
    return dao_create_or_update_annual_billing_for_year(
        service.id,
        next_free_sms_fragment_allowance,
        year_start,
        high_volume_service_last_year=high_volume_service_last_year,
        has_custom_allowance=has_custom_allowance,
        _autocommit=_autocommit,
    )


def _is_high_volume_service(service):
    return get_sms_fragments_sent_last_financial_year(service.id) >= HIGH_VOLUME_SERVICE_THRESHOLD
