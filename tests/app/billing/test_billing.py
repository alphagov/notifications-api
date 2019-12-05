from calendar import monthrange
from datetime import datetime, timedelta
import json

import pytest
from freezegun import freeze_time

from app.models import FactBilling
from app.dao.date_util import get_current_financial_year_start_year, get_month_start_and_end_date_in_utc
from app.dao.annual_billing_dao import dao_get_free_sms_fragment_limit_for_year
from tests.app.db import (
    create_notification,
    create_rate,
    create_annual_billing,
    create_template,
    create_service,
    create_ft_billing
)
from app.billing.rest import update_free_sms_fragment_limit_data

from tests import create_authorization_header

APR_2016_MONTH_START = datetime(2016, 3, 31, 23, 00, 00)
APR_2016_MONTH_END = datetime(2016, 4, 30, 22, 59, 59, 99999)

IN_MAY_2016 = datetime(2016, 5, 10, 23, 00, 00)
IN_JUN_2016 = datetime(2016, 6, 3, 23, 00, 00)


def _assert_dict_equals(actual, expected_dict):
    assert actual == expected_dict


def test_create_update_free_sms_fragment_limit_invalid_schema(client, sample_service):

    response = client.post('service/{}/billing/free-sms-fragment-limit'.format(sample_service.id),
                           data={},
                           headers=[('Content-Type', 'application/json'), create_authorization_header()])
    json_resp = json.loads(response.get_data(as_text=True))

    assert response.status_code == 400
    assert 'JSON' in json_resp['message']


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


def test_get_free_sms_fragment_limit_current_year_creates_new_row(client, sample_service):

    current_year = get_current_financial_year_start_year()
    create_annual_billing(sample_service.id, 9999, current_year - 1)

    response_get = client.get(
        'service/{}/billing/free-sms-fragment-limit'.format(sample_service.id),
        headers=[('Content-Type', 'application/json'), create_authorization_header()])

    json_resp = json.loads(response_get.get_data(as_text=True))
    assert response_get.status_code == 200
    assert json_resp['financial_year_start'] == get_current_financial_year_start_year()
    assert json_resp['free_sms_fragment_limit'] == 9999


def test_get_free_sms_fragment_limit_past_year_not_exist(client, sample_service):
    current_year = get_current_financial_year_start_year()
    create_annual_billing(sample_service.id, 9999, current_year - 1)
    create_annual_billing(sample_service.id, 10000, current_year + 1)

    annual_billing = dao_get_free_sms_fragment_limit_for_year(sample_service.id, current_year - 2)
    assert annual_billing is None

    res_get = client.get(
        'service/{}/billing/free-sms-fragment-limit?financial_year_start={}'
        .format(sample_service.id, current_year - 2),
        headers=[('Content-Type', 'application/json'), create_authorization_header()])
    json_resp = json.loads(res_get.get_data(as_text=True))

    assert res_get.status_code == 200
    assert json_resp['financial_year_start'] == current_year - 1
    assert json_resp['free_sms_fragment_limit'] == 9999


def test_get_free_sms_fragment_limit_future_year_not_exist(client, sample_service):
    current_year = get_current_financial_year_start_year()
    create_annual_billing(sample_service.id, free_sms_fragment_limit=9999, financial_year_start=current_year - 1)
    create_annual_billing(sample_service.id, free_sms_fragment_limit=10000, financial_year_start=current_year + 1)

    annual_billing = dao_get_free_sms_fragment_limit_for_year(sample_service.id, current_year + 2)
    assert annual_billing is None

    res_get = client.get(
        'service/{}/billing/free-sms-fragment-limit?financial_year_start={}'
        .format(sample_service.id, current_year + 2),
        headers=[('Content-Type', 'application/json'), create_authorization_header()])
    json_resp = json.loads(res_get.get_data(as_text=True))

    assert res_get.status_code == 200
    assert json_resp['financial_year_start'] == current_year + 2
    assert json_resp['free_sms_fragment_limit'] == 10000


def test_update_free_sms_fragment_limit_data(client, sample_service):
    current_year = get_current_financial_year_start_year()
    create_annual_billing(sample_service.id, free_sms_fragment_limit=250000, financial_year_start=current_year - 1)

    update_free_sms_fragment_limit_data(sample_service.id, 9999, current_year)

    annual_billing = dao_get_free_sms_fragment_limit_for_year(sample_service.id, current_year)
    assert annual_billing.free_sms_fragment_limit == 9999


@freeze_time('2018-04-21 14:00')
def test_get_yearly_usage_by_monthly_from_ft_billing_populates_deltas(client, notify_db_session):
    service = create_service()
    sms_template = create_template(service=service, template_type="sms")
    create_rate(start_date=datetime.utcnow() - timedelta(days=1), value=0.158, notification_type='sms')

    create_notification(template=sms_template, status='delivered')

    assert FactBilling.query.count() == 0

    response = client.get('service/{}/billing/ft-monthly-usage?year=2018'.format(service.id),
                          headers=[('Content-Type', 'application/json'), create_authorization_header()])

    assert response.status_code == 200
    assert len(json.loads(response.get_data(as_text=True))) == 1
    fact_billing = FactBilling.query.all()
    assert len(fact_billing) == 1
    assert fact_billing[0].notification_type == 'sms'


def test_get_yearly_usage_by_monthly_from_ft_billing(client, notify_db_session):
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

    response = client.get('service/{}/billing/ft-monthly-usage?year=2016'.format(service.id),
                          headers=[('Content-Type', 'application/json'), create_authorization_header()])

    json_resp = json.loads(response.get_data(as_text=True))
    ft_letters = [x for x in json_resp if x['notification_type'] == 'letter']
    ft_sms = [x for x in json_resp if x['notification_type'] == 'sms']
    ft_email = [x for x in json_resp if x['notification_type'] == 'email']
    keys = [x.keys() for x in ft_sms][0]
    expected_sms_april = {"month": "April",
                          "notification_type": "sms",
                          "billing_units": 30,
                          "rate": 0.162,
                          "postage": "none"
                          }
    expected_letter_april = {"month": "April",
                             "notification_type": "letter",
                             "billing_units": 30,
                             "rate": 0.33,
                             "postage": "second"
                             }

    for k in keys:
        assert ft_sms[0][k] == expected_sms_april[k]
        assert ft_letters[0][k] == expected_letter_april[k]
    assert len(ft_email) == 0


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
                              template=sms_template,
                              rate_multiplier=2,
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
    return service


def test_get_yearly_billing_usage_summary_from_ft_billing_returns_400_if_missing_year(client, sample_service):
    response = client.get(
        '/service/{}/billing/ft-yearly-usage-summary'.format(sample_service.id),
        headers=[create_authorization_header()]
    )
    assert response.status_code == 400
    assert json.loads(response.get_data(as_text=True)) == {
        'message': 'No valid year provided', 'result': 'error'
    }


def test_get_yearly_billing_usage_summary_from_ft_billing_returns_empty_list_if_no_billing_data(
        client, sample_service
):
    response = client.get(
        '/service/{}/billing/ft-yearly-usage-summary?year=2016'.format(sample_service.id),
        headers=[create_authorization_header()]
    )
    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True)) == []


def test_get_yearly_billing_usage_summary_from_ft_billing(client, notify_db_session):
    service = set_up_yearly_data()

    response = client.get('/service/{}/billing/ft-yearly-usage-summary?year=2016'.format(service.id),
                          headers=[create_authorization_header()]
                          )
    assert response.status_code == 200
    json_response = json.loads(response.get_data(as_text=True))
    assert len(json_response) == 3
    assert json_response[0]['notification_type'] == 'email'
    assert json_response[0]['billing_units'] == 275
    assert json_response[0]['rate'] == 0
    assert json_response[0]['letter_total'] == 0
    assert json_response[1]['notification_type'] == 'letter'
    assert json_response[1]['billing_units'] == 275
    assert json_response[1]['rate'] == 0.33
    assert json_response[1]['letter_total'] == 90.75
    assert json_response[2]['notification_type'] == 'sms'
    assert json_response[2]['billing_units'] == 825
    assert json_response[2]['rate'] == 0.0162
    assert json_response[2]['letter_total'] == 0


def test_get_yearly_usage_by_monthly_from_ft_billing_all_cases(client, notify_db_session):
    service = set_up_data_for_all_cases()
    response = client.get('service/{}/billing/ft-monthly-usage?year=2018'.format(service.id),
                          headers=[('Content-Type', 'application/json'), create_authorization_header()])

    assert response.status_code == 200
    json_response = json.loads(response.get_data(as_text=True))
    assert len(json_response) == 5
    assert json_response[0]['month'] == 'May'
    assert json_response[0]['notification_type'] == 'letter'
    assert json_response[0]['rate'] == 0.33
    assert json_response[0]['billing_units'] == 1
    assert json_response[0]['postage'] == 'second'

    assert json_response[1]['month'] == 'May'
    assert json_response[1]['notification_type'] == 'letter'
    assert json_response[1]['rate'] == 0.36
    assert json_response[1]['billing_units'] == 1
    assert json_response[1]['postage'] == 'second'

    assert json_response[2]['month'] == 'May'
    assert json_response[2]['notification_type'] == 'letter'
    assert json_response[2]['rate'] == 0.39
    assert json_response[2]['billing_units'] == 1
    assert json_response[2]['postage'] == 'first'

    assert json_response[3]['month'] == 'May'
    assert json_response[3]['notification_type'] == 'sms'
    assert json_response[3]['rate'] == 0.0150
    assert json_response[3]['billing_units'] == 4
    assert json_response[3]['postage'] == 'none'

    assert json_response[4]['month'] == 'May'
    assert json_response[4]['notification_type'] == 'sms'
    assert json_response[4]['rate'] == 0.162
    assert json_response[4]['billing_units'] == 5
    assert json_response[4]['postage'] == 'none'


def test_get_yearly_billing_usage_summary_from_ft_billing_all_cases(client, notify_db_session):
    service = set_up_data_for_all_cases()
    response = client.get('/service/{}/billing/ft-yearly-usage-summary?year=2018'.format(service.id),
                          headers=[create_authorization_header()])
    assert response.status_code == 200
    json_response = json.loads(response.get_data(as_text=True))

    assert len(json_response) == 6
    assert json_response[0]["notification_type"] == 'email'
    assert json_response[0]["billing_units"] == 1
    assert json_response[0]["rate"] == 0
    assert json_response[0]["letter_total"] == 0

    assert json_response[1]["notification_type"] == 'letter'
    assert json_response[1]["billing_units"] == 1
    assert json_response[1]["rate"] == 0.33
    assert json_response[1]["letter_total"] == 0.33

    assert json_response[2]["notification_type"] == 'letter'
    assert json_response[2]["billing_units"] == 1
    assert json_response[2]["rate"] == 0.36
    assert json_response[2]["letter_total"] == 0.36

    assert json_response[3]["notification_type"] == 'letter'
    assert json_response[3]["billing_units"] == 1
    assert json_response[3]["rate"] == 0.39
    assert json_response[3]["letter_total"] == 0.39

    assert json_response[4]["notification_type"] == 'sms'
    assert json_response[4]["billing_units"] == 4
    assert json_response[4]["rate"] == 0.0150
    assert json_response[4]["letter_total"] == 0

    assert json_response[5]["notification_type"] == 'sms'
    assert json_response[5]["billing_units"] == 5
    assert json_response[5]["rate"] == 0.162
    assert json_response[5]["letter_total"] == 0


def set_up_data_for_all_cases():
    service = create_service()
    sms_template = create_template(service=service, template_type="sms")
    email_template = create_template(service=service, template_type="email")
    letter_template = create_template(service=service, template_type="letter")
    create_ft_billing(bst_date='2018-05-16',
                      template=sms_template,
                      rate_multiplier=1,
                      international=False,
                      rate=0.162,
                      billable_unit=1,
                      notifications_sent=1)
    create_ft_billing(bst_date='2018-05-17',
                      template=sms_template,
                      rate_multiplier=2,
                      international=False,
                      rate=0.162,
                      billable_unit=2,
                      notifications_sent=1)
    create_ft_billing(bst_date='2018-05-16',
                      template=sms_template,
                      rate_multiplier=2,
                      international=False,
                      rate=0.0150,
                      billable_unit=2,
                      notifications_sent=1)
    create_ft_billing(bst_date='2018-05-16',
                      template=email_template,
                      rate_multiplier=1,
                      international=False,
                      rate=0,
                      billable_unit=0,
                      notifications_sent=1)
    create_ft_billing(bst_date='2018-05-16',
                      template=letter_template,
                      rate_multiplier=1,
                      international=False,
                      rate=0.33,
                      billable_unit=1,
                      notifications_sent=1,
                      postage='second')
    create_ft_billing(bst_date='2018-05-17',
                      template=letter_template,
                      rate_multiplier=1,
                      international=False,
                      rate=0.36,
                      billable_unit=2,
                      notifications_sent=1,
                      postage='second')
    create_ft_billing(bst_date='2018-05-18',
                      template=letter_template,
                      rate_multiplier=1,
                      international=False,
                      rate=0.39,
                      billable_unit=3,
                      notifications_sent=1,
                      postage='first')
    return service
