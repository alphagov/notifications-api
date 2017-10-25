from app.service.utils import get_current_financial_year_start_year
from app.models import AnnualBilling
from app.dao.annual_billing_dao import (
    dao_create_or_update_annual_billing_for_year,
    dao_get_free_sms_fragment_limit_for_year
)


def test_sample_service_has_free_sms_fragment_limit(notify_db_session, sample_service):

    # when sample_service was created, it automatically create an entry in the annual_billing table
    free_limit = dao_get_free_sms_fragment_limit_for_year(sample_service.id, get_current_financial_year_start_year())

    assert free_limit.free_sms_fragment_limit == 250000
    assert free_limit.financial_year_start == get_current_financial_year_start_year()
    assert free_limit.service_id == sample_service.id


def test_dao_update_free_sms_fragment_limit(notify_db_session, sample_service):
    year = 1999
    old_limit = 1000
    new_limit = 9999

    data = AnnualBilling(
        free_sms_fragment_limit=old_limit,
        financial_year_start=year,
        service_id=sample_service.id,
    )

    dao_create_or_update_annual_billing_for_year(data)
    data.free_sms_fragment_limit = new_limit
    dao_create_or_update_annual_billing_for_year(data)
    new_free_limit = dao_get_free_sms_fragment_limit_for_year(sample_service.id, year)

    assert new_free_limit.free_sms_fragment_limit == new_limit
