from app import db, create_uuid
from app.dao.dao_utils import (
    transactional,
    version_class
)
from app.models import AnnualBilling
from datetime import datetime
from app.service.utils import get_current_financial_year_start_year


def dao_get_annual_billing(service_id):
    return AnnualBilling.query.filter_by(
        service_id=service_id,
    ).all()


def dao_create_or_update_annual_billing_for_year(annual_billing):
    db.session.add(annual_billing)
    db.session.commit()


def dao_get_free_sms_fragment_limit_for_year(service_id, year):

    return AnnualBilling.query.filter_by(
        service_id=service_id,
        financial_year_start=year
    ).first()


def dao_get_all_free_sms_fragment_limit(service_id):

    return AnnualBilling.query.filter_by(
        service_id=service_id,
    ).all()


def insert_annual_billing(service):
    """
    This method is called from create_service which is wrapped in a transaction.
    """
    annual_billing = AnnualBilling(
        free_sms_fragment_limit=service.free_sms_fragment_limit,
        financial_year_start=get_current_financial_year_start_year(),
        service=service,
    )

    db.session.add(annual_billing)
