from app.dao.date_util import get_current_financial_year_start_year

from app.dao.annual_billing_dao import (
    dao_create_or_update_annual_billing_for_year,
    dao_get_free_sms_fragment_limit_for_year,
    dao_update_annual_billing_for_current_and_future_years,
)
from tests.app.db import create_annual_billing


def test_get_sample_service_has_default_free_sms_fragment_limit(notify_db_session, sample_service):

    # when sample_service was created, it automatically create an entry in the annual_billing table
    free_limit = dao_get_free_sms_fragment_limit_for_year(sample_service.id, get_current_financial_year_start_year())

    assert free_limit.free_sms_fragment_limit == 250000
    assert free_limit.financial_year_start == get_current_financial_year_start_year()
    assert free_limit.service_id == sample_service.id


def test_dao_update_free_sms_fragment_limit(notify_db_session, sample_service):
    new_limit = 9999
    year = get_current_financial_year_start_year()
    dao_create_or_update_annual_billing_for_year(sample_service.id, new_limit, year)
    new_free_limit = dao_get_free_sms_fragment_limit_for_year(sample_service.id, year)

    assert new_free_limit.free_sms_fragment_limit == new_limit


def test_create_annual_billing_not_specify_year(notify_db_session, sample_service):

    dao_create_or_update_annual_billing_for_year(sample_service.id, 9999)

    free_limit = dao_get_free_sms_fragment_limit_for_year(sample_service.id)

    assert free_limit.free_sms_fragment_limit == 9999


def test_create_annual_billing_specify_year(notify_db_session, sample_service):

    dao_create_or_update_annual_billing_for_year(sample_service.id, 9999, 2016)

    free_limit = dao_get_free_sms_fragment_limit_for_year(sample_service.id, 2016)

    assert free_limit.free_sms_fragment_limit == 9999


def test_dao_update_annual_billing_for_current_and_future_years(notify_db_session, sample_service):
    current_year = get_current_financial_year_start_year()
    limits = [240000, 250000, 260000, 270000]
    create_annual_billing(sample_service.id, limits[0], current_year - 1)
    create_annual_billing(sample_service.id, limits[2], current_year + 1)
    create_annual_billing(sample_service.id, limits[3], current_year + 2)

    dao_update_annual_billing_for_current_and_future_years(sample_service.id, 9999, current_year)

    free_limit = dao_get_free_sms_fragment_limit_for_year(sample_service.id, current_year - 1)
    assert free_limit.free_sms_fragment_limit == 240000

    for year in range(current_year, current_year + 3):
        free_limit = dao_get_free_sms_fragment_limit_for_year(sample_service.id, year)
        assert free_limit.free_sms_fragment_limit == 9999
