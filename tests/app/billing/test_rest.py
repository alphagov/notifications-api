from calendar import monthrange
from datetime import datetime

import pytest
from freezegun import freeze_time

from app.billing.rest import update_free_sms_fragment_limit_data
from app.dao.annual_billing_dao import dao_get_free_sms_fragment_limit_for_year
from app.dao.date_util import (
    get_current_financial_year_start_year,
    get_month_start_and_end_date_in_utc,
)
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
        'billing.create_or_update_free_sms_fragment_limit',
        service_id=sample_service.id,
        _data={},
        _expected_status=400
    )

    assert 'errors' in json_response


def test_create_free_sms_fragment_limit_current_year_updates_future_years(admin_request, sample_service):
    current_year = get_current_financial_year_start_year()
    future_billing = create_annual_billing(sample_service.id, 1, current_year + 1)

    admin_request.post(
        'billing.create_or_update_free_sms_fragment_limit',
        service_id=sample_service.id,
        _data={'free_sms_fragment_limit': 9999},
        _expected_status=201
    )

    current_billing = dao_get_free_sms_fragment_limit_for_year(sample_service.id, current_year)
    assert future_billing.free_sms_fragment_limit == 9999
    assert current_billing.financial_year_start == current_year
    assert current_billing.free_sms_fragment_limit == 9999


@pytest.mark.parametrize('update_existing', [True, False])
def test_create_or_update_free_sms_fragment_limit_past_year_doenst_update_other_years(
    admin_request,
    sample_service,
    update_existing
):
    current_year = get_current_financial_year_start_year()
    create_annual_billing(sample_service.id, 1, current_year)
    if update_existing:
        create_annual_billing(sample_service.id, 1, current_year - 1)

    data = {'financial_year_start': current_year - 1, 'free_sms_fragment_limit': 9999}
    admin_request.post(
        'billing.create_or_update_free_sms_fragment_limit',
        service_id=sample_service.id,
        _data=data,
        _expected_status=201)

    assert dao_get_free_sms_fragment_limit_for_year(sample_service.id, current_year - 1).free_sms_fragment_limit == 9999
    assert dao_get_free_sms_fragment_limit_for_year(sample_service.id, current_year).free_sms_fragment_limit == 1


def test_create_free_sms_fragment_limit_updates_existing_year(admin_request, sample_service):
    current_year = get_current_financial_year_start_year()
    annual_billing = create_annual_billing(sample_service.id, 1, current_year)

    admin_request.post(
        'billing.create_or_update_free_sms_fragment_limit',
        service_id=sample_service.id,
        _data={'financial_year_start': current_year, 'free_sms_fragment_limit': 2},
        _expected_status=201)

    assert annual_billing.free_sms_fragment_limit == 2


@freeze_time('2021-04-02 13:00')
def test_get_free_sms_fragment_limit(
    admin_request, sample_service
):
    create_annual_billing(service_id=sample_service.id, free_sms_fragment_limit=11000, financial_year_start=2021)

    json_response = admin_request.get(
        'billing.get_free_sms_fragment_limit',
        service_id=sample_service.id
    )

    assert json_response['financial_year_start'] == 2021
    assert json_response['free_sms_fragment_limit'] == 11000


@freeze_time('2021-04-02 13:00')
def test_get_free_sms_fragment_limit_current_year_creates_new_row_if_annual_billing_is_missing(
    admin_request, sample_service
):
    json_response = admin_request.get(
        'billing.get_free_sms_fragment_limit',
        service_id=sample_service.id
    )

    assert json_response['financial_year_start'] == 2021
    assert json_response['free_sms_fragment_limit'] == 10000  # based on other organisation type


def test_update_free_sms_fragment_limit_data(client, sample_service):
    current_year = get_current_financial_year_start_year()
    create_annual_billing(sample_service.id, free_sms_fragment_limit=250000, financial_year_start=current_year - 1)

    update_free_sms_fragment_limit_data(sample_service.id, 9999, current_year)

    annual_billing = dao_get_free_sms_fragment_limit_for_year(sample_service.id, current_year)
    assert annual_billing.free_sms_fragment_limit == 9999


def set_up_monthly_data():
    service = create_service()
    sms_template = create_template(service=service, template_type="sms")
    email_template = create_template(service=service, template_type="email")
    letter_template = create_template(service=service, template_type="letter")

    for month in range(1, 13):
        mon = str(month).zfill(2)
        for day in range(1, monthrange(2016, month)[1] + 1):
            d = str(day).zfill(2)
            create_ft_billing(bst_date='2016-{}-{}'.format(mon, d),
                              template=sms_template,
                              billable_unit=1,
                              rate=0.162)
            create_ft_billing(bst_date='2016-{}-{}'.format(mon, d),
                              template=email_template,
                              rate=0)
            create_ft_billing(bst_date='2016-{}-{}'.format(mon, d),
                              template=letter_template,
                              billable_unit=1,
                              rate=0.33,
                              postage='second')

    create_annual_billing(service_id=service.id, free_sms_fragment_limit=4, financial_year_start=2016)
    return service


def test_get_yearly_usage_by_monthly_from_ft_billing(admin_request, notify_db_session):
    service = set_up_monthly_data()

    json_response = admin_request.get(
        'billing.get_yearly_usage_by_monthly_from_ft_billing',
        service_id=service.id,
        year=2016
    )

    assert len(json_response) == 18

    email_rows = [row for row in json_response if row['notification_type'] == 'email']
    assert len(email_rows) == 0

    letter_row = next(x for x in json_response if x['notification_type'] == 'letter')
    sms_row = next(x for x in json_response if x['notification_type'] == 'sms')

    assert letter_row["month"] == "April"
    assert letter_row["notification_type"] == "letter"
    assert letter_row["billing_units"] == 30
    assert letter_row["chargeable_units"] == 30
    assert letter_row["notifications_sent"] == 30
    assert letter_row["rate"] == 0.33
    assert letter_row["postage"] == "second"
    assert letter_row["cost"] == 9.9
    assert letter_row["free_allowance_used"] == 0
    assert letter_row["charged_units"] == 30

    assert sms_row["month"] == "April"
    assert sms_row["notification_type"] == "sms"
    assert sms_row["billing_units"] == 30
    assert sms_row["chargeable_units"] == 30
    assert sms_row["notifications_sent"] == 30
    assert sms_row["rate"] == 0.162
    assert sms_row["postage"] == "none"
    # free allowance is 4, so (30 - 4) * 0.162
    assert sms_row["cost"] == 4.212
    assert sms_row["free_allowance_used"] == 4
    assert sms_row["charged_units"] == 26


def set_up_yearly_data():
    service = create_service()
    sms_template = create_template(service=service, template_type="sms")
    email_template = create_template(service=service, template_type="email")
    letter_template = create_template(service=service, template_type="letter")

    for month in range(1, 13):
        mon = str(month).zfill(2)
        for day in range(1, monthrange(2016, month)[1] + 1):
            d = str(day).zfill(2)
            create_ft_billing(bst_date='2016-{}-{}'.format(mon, d),
                              template=sms_template,
                              rate=0.0162)
            create_ft_billing(bst_date='2016-{}-{}'.format(mon, d),
                              template=email_template,
                              billable_unit=0,
                              rate=0)
            create_ft_billing(bst_date='2016-{}-{}'.format(mon, d),
                              template=letter_template,
                              rate=0.33,
                              postage='second')
        start_date, end_date = get_month_start_and_end_date_in_utc(datetime(2016, int(mon), 1))

    create_annual_billing(service_id=service.id, free_sms_fragment_limit=4, financial_year_start=2016)
    return service


def test_get_yearly_billing_usage_summary_from_ft_billing_returns_400_if_missing_year(admin_request, sample_service):
    json_response = admin_request.get(
        'billing.get_yearly_billing_usage_summary_from_ft_billing',
        service_id=sample_service.id,
        _expected_status=400
    )
    assert json_response == {
        'message': 'No valid year provided', 'result': 'error'
    }


def test_get_yearly_billing_usage_summary_from_ft_billing_returns_empty_list_if_no_billing_data(
    admin_request, sample_service
):
    json_response = admin_request.get(
        'billing.get_yearly_billing_usage_summary_from_ft_billing',
        service_id=sample_service.id,
        year=2016
    )
    assert json_response == []


def test_get_yearly_billing_usage_summary_from_ft_billing(admin_request, notify_db_session):
    service = set_up_yearly_data()

    json_response = admin_request.get(
        'billing.get_yearly_billing_usage_summary_from_ft_billing',
        service_id=service.id,
        year=2016
    )

    assert len(json_response) == 3

    assert json_response[0]['notification_type'] == 'email'
    assert json_response[0]['billing_units'] == 275
    assert json_response[0]['chargeable_units'] == 0
    assert json_response[0]['notifications_sent'] == 275
    assert json_response[0]['rate'] == 0
    assert json_response[0]['letter_total'] == 0
    assert json_response[0]['cost'] == 0
    assert json_response[0]['free_allowance_used'] == 0
    assert json_response[0]['charged_units'] == 0

    assert json_response[1]['notification_type'] == 'letter'
    assert json_response[1]['billing_units'] == 275
    assert json_response[1]['chargeable_units'] == 275
    assert json_response[1]['notifications_sent'] == 275
    assert json_response[1]['rate'] == 0.33
    assert json_response[1]['letter_total'] == 90.75
    assert json_response[1]['cost'] == 90.75
    assert json_response[1]['free_allowance_used'] == 0
    assert json_response[1]['charged_units'] == 275

    assert json_response[2]['notification_type'] == 'sms'
    assert json_response[2]['billing_units'] == 275
    assert json_response[2]['chargeable_units'] == 275
    assert json_response[2]['notifications_sent'] == 275
    assert json_response[2]['rate'] == 0.0162
    assert json_response[2]['letter_total'] == 0
    assert json_response[2]['cost'] == 4.3902
    assert json_response[2]['free_allowance_used'] == 4
    assert json_response[2]['charged_units'] == 271
