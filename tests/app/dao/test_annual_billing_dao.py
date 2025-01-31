import datetime

import pytest
from freezegun import freeze_time

from app.dao.annual_billing_dao import (
    dao_create_or_update_annual_billing_for_year,
    dao_get_default_annual_allowance_for_service,
    dao_get_free_sms_fragment_limit_for_year,
    set_default_free_allowance_for_service,
)
from app.dao.date_util import get_current_financial_year_start_year
from app.models import AnnualBilling
from tests.app.db import create_service


def test_dao_update_free_sms_fragment_limit(notify_db_session, sample_service):
    new_limit = 9999
    year = get_current_financial_year_start_year()
    dao_create_or_update_annual_billing_for_year(sample_service.id, new_limit, year)
    new_free_limit = dao_get_free_sms_fragment_limit_for_year(sample_service.id, year)

    assert new_free_limit.free_sms_fragment_limit == new_limit


def test_create_annual_billing(sample_service):
    dao_create_or_update_annual_billing_for_year(sample_service.id, 9999, 2016)

    free_limit = dao_get_free_sms_fragment_limit_for_year(sample_service.id, 2016)

    assert free_limit.free_sms_fragment_limit == 9999


def test_dao_get_default_annual_allowance_for_service_uses_org_default(sample_service, caplog):
    assert sample_service.organisation_type is None

    with caplog.at_level("WARN"):
        default_allowance = dao_get_default_annual_allowance_for_service(sample_service, 2024)
        assert default_allowance.allowance == 5000

    assert (
        f"No organisation type for service {sample_service.id}. Using default for `other` org type."
    ) in caplog.messages


@pytest.mark.parametrize(
    "org_type, year, expected_allowance",
    [
        ("central", 2024, 30_000),
        ("nhs_gp", 2024, 0),
        ("nhs_local", 2022, 20_000),
        ("emergency_service", 2023, 20_000),
    ],
)
def test_dao_get_default_annual_allowance_for_service(sample_service, org_type, year, expected_allowance):
    sample_service.organisation_type = org_type
    default_allowance = dao_get_default_annual_allowance_for_service(sample_service, year)
    assert default_allowance.allowance == expected_allowance


@pytest.mark.parametrize(
    "org_type, year, expected_default",
    [
        ("central", 2021, 150000),
        ("local", 2021, 25000),
        ("nhs_central", 2021, 150000),
        ("nhs_local", 2021, 25000),
        ("nhs_gp", 2021, 10000),
        ("emergency_service", 2021, 25000),
        ("school_or_college", 2021, 10000),
        ("other", 2021, 10000),
        (None, 2021, 10000),
        ("central", 2020, 250000),
        ("local", 2020, 25000),
        ("nhs_central", 2020, 250000),
        ("nhs_local", 2020, 25000),
        ("nhs_gp", 2020, 25000),
        ("emergency_service", 2020, 25000),
        ("school_or_college", 2020, 25000),
        ("other", 2020, 25000),
        (None, 2020, 25000),
        ("central", 2019, 250000),
        ("school_or_college", 2022, 10000),
        ("central", 2022, 40000),
        ("local", 2022, 20000),
        ("nhs_local", 2022, 20000),
        ("emergency_service", 2022, 20000),
        ("central", 2023, 40000),
        # Some test cases that will make valid assertions as time inevitably marches on
        ("central", get_current_financial_year_start_year(), 30_000),
        ("local", get_current_financial_year_start_year(), 10_000),
        ("nhs_central", get_current_financial_year_start_year(), 30_000),
        ("nhs_local", get_current_financial_year_start_year(), 10_000),
        ("nhs_gp", get_current_financial_year_start_year(), 0),
        ("emergency_service", get_current_financial_year_start_year(), 10_000),
        ("school_or_college", get_current_financial_year_start_year(), 5_000),
        ("other", get_current_financial_year_start_year(), 5_000),
        (None, get_current_financial_year_start_year(), 5_000),
    ],
)
def test_set_default_free_allowance_for_service(notify_db_session, org_type, year, expected_default):
    service = create_service(organisation_type=org_type)

    set_default_free_allowance_for_service(service=service, year_start=year)

    annual_billing = AnnualBilling.query.all()

    assert len(annual_billing) == 1
    assert annual_billing[0].service_id == service.id
    assert annual_billing[0].financial_year_start == year
    assert annual_billing[0].free_sms_fragment_limit == expected_default


def test_set_default_free_allowance_for_service_fails_before_2016(notify_db_session):
    service = create_service(organisation_type="central")

    with pytest.raises(ValueError) as e:
        set_default_free_allowance_for_service(service=service, year_start=2015)

    assert str(e.value) == "year_start before 2016 is invalid"


def test_set_default_free_allowance_for_service_fails_for_future_year(notify_db_session):
    service = create_service(organisation_type="central")

    with pytest.raises(ValueError) as e:
        set_default_free_allowance_for_service(service=service, year_start=datetime.date.today().year + 1)

    assert str(e.value) == "year_start cannot be in a future financial year"


@freeze_time("2021-03-29 14:02:00")
def test_set_default_free_allowance_for_service_using_correct_year(sample_service, mocker):
    mock_dao = mocker.patch("app.dao.annual_billing_dao.dao_create_or_update_annual_billing_for_year")
    set_default_free_allowance_for_service(service=sample_service, year_start=None)

    mock_dao.assert_called_once_with(sample_service.id, 25000, 2020)


@freeze_time("2021-04-01 14:02:00")
def test_set_default_free_allowance_for_service_updates_existing_year(sample_service):
    set_default_free_allowance_for_service(service=sample_service, year_start=None)
    annual_billing = AnnualBilling.query.all()
    assert not sample_service.organisation_type
    assert len(annual_billing) == 1
    assert annual_billing[0].service_id == sample_service.id
    assert annual_billing[0].free_sms_fragment_limit == 10000

    sample_service.organisation_type = "central"

    set_default_free_allowance_for_service(service=sample_service, year_start=None)
    annual_billing = AnnualBilling.query.all()
    assert len(annual_billing) == 1
    assert annual_billing[0].service_id == sample_service.id
    assert annual_billing[0].free_sms_fragment_limit == 150000
