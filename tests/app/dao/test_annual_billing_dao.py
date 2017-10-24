# from datetime import datetime, timedelta
# import uuid
# import functools
# import pytest

from app.models import AnnualBilling
from app.dao.annual_billing_dao import (
    dao_create_or_update_annual_billing_for_year,
    dao_get_free_sms_fragment_limit_for_year
)


def test_dao_create_get_free_sms_fragment_limit(notify_db_session, sample_service):
    years = [2015, 2016, 2017]
    free_limit_data = [1000, 2000, 3000]
    for i in range(0, len(years)):
        data = AnnualBilling(
            free_sms_fragment_limit=free_limit_data[i],
            financial_year_start=years[i],
            service_id=sample_service.id,
        )
        dao_create_or_update_annual_billing_for_year(data)

    for i in range(0, len(years)):
        free_limit = dao_get_free_sms_fragment_limit_for_year(sample_service.id, years[i])

        assert free_limit.free_sms_fragment_limit == free_limit_data[i]
        assert free_limit.financial_year_start == years[i]
        assert free_limit.service_id == sample_service.id


def test_dao_update_free_sms_fragment_limit(notify_db_session, sample_service):
    year = 2016
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
