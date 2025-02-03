from datetime import date, datetime

import pytest
from freezegun import freeze_time

from app.billing.rest import update_free_sms_fragment_limit_data
from app.dao.annual_billing_dao import dao_get_free_sms_fragment_limit_for_year
from app.dao.date_util import get_current_financial_year_start_year
from tests.app.db import (
    create_annual_billing,
    create_ft_billing,
    create_service,
    create_template,
)

APR_2016_MONTH_START = datetime(2016, 3, 31, 23, 00, 00)
APR_2016_MONTH_END = datetime(2016, 4, 30, 22, 59, 59, 99999)

IN_MAY_2016 = datetime(2016, 5, 10, 23, 00, 00)
IN_JUN_2016 = datetime(2016, 6, 3, 23, 00, 00)


def test_create_update_free_sms_fragment_limit_invalid_schema(admin_request, sample_service):
    json_response = admin_request.post(
        "billing.create_or_update_free_sms_fragment_limit", service_id=sample_service.id, _data={}, _expected_status=400
    )

    assert "errors" in json_response


def test_create_or_update_free_sms_fragment_limit_past_year_doesnt_update_other_years(admin_request, sample_service):
    current_year = get_current_financial_year_start_year()
    create_annual_billing(sample_service.id, 1, current_year)
    create_annual_billing(sample_service.id, 1, current_year - 1)

    admin_request.post(
        "billing.create_or_update_free_sms_fragment_limit",
        service_id=sample_service.id,
        _data={"free_sms_fragment_limit": 9999},
        _expected_status=201,
    )

    annual_billing_last_year = dao_get_free_sms_fragment_limit_for_year(sample_service.id, current_year - 1)
    assert annual_billing_last_year.free_sms_fragment_limit == 1
    assert annual_billing_last_year.has_custom_allowance is False

    annual_billing_this_year = dao_get_free_sms_fragment_limit_for_year(sample_service.id, current_year)
    assert annual_billing_this_year.free_sms_fragment_limit == 9999
    assert annual_billing_this_year.has_custom_allowance is True


def test_create_free_sms_fragment_limit_updates_existing_year(admin_request, sample_service):
    current_year = get_current_financial_year_start_year()
    annual_billing = create_annual_billing(sample_service.id, 1, current_year)

    admin_request.post(
        "billing.create_or_update_free_sms_fragment_limit",
        service_id=sample_service.id,
        _data={"free_sms_fragment_limit": 2},
        _expected_status=201,
    )

    assert annual_billing.free_sms_fragment_limit == 2
    assert annual_billing.has_custom_allowance is True


@freeze_time("2021-04-02 13:00")
def test_get_free_sms_fragment_limit(admin_request, sample_service):
    create_annual_billing(service_id=sample_service.id, free_sms_fragment_limit=11000, financial_year_start=2021)

    json_response = admin_request.get("billing.get_free_sms_fragment_limit", service_id=sample_service.id)

    assert json_response["financial_year_start"] == 2021
    assert json_response["free_sms_fragment_limit"] == 11000


def test_get_free_sms_fragment_limit_for_pre_notify_year_400s(admin_request, sample_service):
    admin_request.get(
        "billing.get_free_sms_fragment_limit",
        service_id=sample_service.id,
        financial_year_start=2015,
        _expected_status=400,
    )


def test_get_free_sms_fragment_limit_for_future_year_400s(admin_request, sample_service):
    admin_request.get(
        "billing.get_free_sms_fragment_limit",
        service_id=sample_service.id,
        financial_year_start=date.today().year + 1,
        _expected_status=400,
    )


@freeze_time("2021-04-02 13:00")
def test_get_free_sms_fragment_limit_current_year_creates_new_row_if_annual_billing_is_missing(
    admin_request, sample_service
):
    json_response = admin_request.get("billing.get_free_sms_fragment_limit", service_id=sample_service.id)

    assert json_response["financial_year_start"] == 2021
    assert json_response["free_sms_fragment_limit"] == 10000  # based on other organisation type


@pytest.mark.parametrize("high_volume_service_last_year", [True, False])
def test_update_free_sms_fragment_limit_data(client, sample_service, high_volume_service_last_year):
    current_year = get_current_financial_year_start_year()
    create_annual_billing(
        sample_service.id,
        free_sms_fragment_limit=250000,
        financial_year_start=current_year,
        high_volume_service_last_year=high_volume_service_last_year,
    )

    update_free_sms_fragment_limit_data(sample_service.id, 9999)

    annual_billing = dao_get_free_sms_fragment_limit_for_year(sample_service.id, current_year)
    assert annual_billing.free_sms_fragment_limit == 9999
    assert annual_billing.high_volume_service_last_year is high_volume_service_last_year
    assert annual_billing.has_custom_allowance is True


def test_update_free_sms_fragment_limit_data_when_updating_to_default(sample_service, mocker):
    mocker.patch("app.billing.rest.dao_get_default_annual_allowance_for_service", return_value=50)

    current_year = get_current_financial_year_start_year()
    create_annual_billing(
        sample_service.id,
        free_sms_fragment_limit=250000,
        financial_year_start=current_year - 1,
        has_custom_allowance=True,
    )

    update_free_sms_fragment_limit_data(sample_service.id, 50)

    annual_billing = dao_get_free_sms_fragment_limit_for_year(sample_service.id, current_year)
    assert annual_billing.free_sms_fragment_limit == 50
    assert annual_billing.high_volume_service_last_year is False
    assert annual_billing.has_custom_allowance is False


def test_get_yearly_usage_by_monthly_from_ft_billing(admin_request, notify_db_session):
    service = create_service()
    create_annual_billing(service_id=service.id, free_sms_fragment_limit=1, financial_year_start=2016)

    sms_template = create_template(service=service, template_type="sms")
    email_template = create_template(service=service, template_type="email")
    letter_template = create_template(service=service, template_type="letter")

    for dt in (date(2016, 4, 28), date(2016, 11, 10), date(2017, 2, 26)):
        create_ft_billing(bst_date=dt, template=sms_template, rate=0.0162)
        create_ft_billing(bst_date=dt, template=email_template, billable_unit=0, rate=0)
        create_ft_billing(bst_date=dt, template=letter_template, rate=0.33, postage="second")

    json_response = admin_request.get(
        "billing.get_yearly_usage_by_monthly_from_ft_billing", service_id=service.id, year=2016
    )

    assert len(json_response) == 6  # 3 billed months for SMS and letters

    email_rows = [row for row in json_response if row["notification_type"] == "email"]
    assert len(email_rows) == 0

    letter_row = next(x for x in json_response if x["notification_type"] == "letter")
    sms_row = next(x for x in json_response if x["notification_type"] == "sms")

    assert letter_row["month"] == "April"
    assert letter_row["notification_type"] == "letter"
    assert letter_row["chargeable_units"] == 1
    assert letter_row["notifications_sent"] == 1
    assert letter_row["rate"] == 0.33
    assert letter_row["postage"] == "second"
    assert letter_row["cost"] == 0.33
    assert letter_row["free_allowance_used"] == 0
    assert letter_row["charged_units"] == 1

    assert sms_row["month"] == "April"
    assert sms_row["notification_type"] == "sms"
    assert sms_row["chargeable_units"] == 1
    assert sms_row["notifications_sent"] == 1
    assert sms_row["rate"] == 0.0162
    assert sms_row["postage"] == "none"
    # free allowance is 1
    assert sms_row["cost"] == 0
    assert sms_row["free_allowance_used"] == 1
    assert sms_row["charged_units"] == 0


def test_get_yearly_billing_usage_summary_from_ft_billing_returns_400_if_missing_year(admin_request, sample_service):
    json_response = admin_request.get(
        "billing.get_yearly_billing_usage_summary_from_ft_billing", service_id=sample_service.id, _expected_status=400
    )
    assert json_response == {"message": "No valid year provided", "result": "error"}


def test_get_yearly_billing_usage_summary_from_ft_billing_returns_empty_list_if_no_billing_data(
    admin_request, sample_service
):
    json_response = admin_request.get(
        "billing.get_yearly_billing_usage_summary_from_ft_billing", service_id=sample_service.id, year=2016
    )
    assert json_response == []


def test_get_yearly_billing_usage_summary_from_ft_billing(admin_request, notify_db_session):
    service = create_service()
    create_annual_billing(service_id=service.id, free_sms_fragment_limit=1, financial_year_start=2016)

    sms_template = create_template(service=service, template_type="sms")
    email_template = create_template(service=service, template_type="email")
    letter_template = create_template(service=service, template_type="letter")

    for dt in (date(2016, 4, 28), date(2016, 11, 10), date(2017, 2, 26)):
        create_ft_billing(bst_date=dt, template=sms_template, rate=0.0162)
        create_ft_billing(bst_date=dt, template=email_template, billable_unit=0, rate=0)
        create_ft_billing(bst_date=dt, template=letter_template, rate=0.33, postage="second")

    json_response = admin_request.get(
        "billing.get_yearly_billing_usage_summary_from_ft_billing", service_id=service.id, year=2016
    )

    assert len(json_response) == 3

    assert json_response[0]["notification_type"] == "email"
    assert json_response[0]["chargeable_units"] == 0
    assert json_response[0]["notifications_sent"] == 3
    assert json_response[0]["rate"] == 0
    assert json_response[0]["cost"] == 0
    assert json_response[0]["free_allowance_used"] == 0
    assert json_response[0]["charged_units"] == 0

    assert json_response[1]["notification_type"] == "letter"
    assert json_response[1]["chargeable_units"] == 3
    assert json_response[1]["notifications_sent"] == 3
    assert json_response[1]["rate"] == 0.33
    assert json_response[1]["cost"] == 0.99
    assert json_response[1]["free_allowance_used"] == 0
    assert json_response[1]["charged_units"] == 3

    assert json_response[2]["notification_type"] == "sms"
    assert json_response[2]["chargeable_units"] == 3
    assert json_response[2]["notifications_sent"] == 3
    assert json_response[2]["rate"] == 0.0162
    assert json_response[2]["cost"] == 0.0324
    assert json_response[2]["free_allowance_used"] == 1
    assert json_response[2]["charged_units"] == 2
