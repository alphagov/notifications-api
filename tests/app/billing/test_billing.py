from datetime import datetime, timedelta
import json

import pytest

from app.billing.rest import _transform_billing_for_month_sms
from app.dao.monthly_billing_dao import (
    create_or_update_monthly_billing,
    get_monthly_billing_by_notification_type,
)
from app.models import SMS_TYPE, EMAIL_TYPE, LETTER_TYPE
from app.dao.date_util import get_current_financial_year_start_year
from app.dao.annual_billing_dao import dao_get_free_sms_fragment_limit_for_year
from tests.app.db import (
    create_notification,
    create_rate,
    create_monthly_billing_entry,
    create_annual_billing,
    create_letter_rate,
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


def test_get_yearly_billing_summary_returns_correct_breakdown(client, sample_template):
    create_rate(start_date=IN_MAY_2016 - timedelta(days=1), value=0.12, notification_type=SMS_TYPE)
    create_notification(
        template=sample_template, created_at=IN_MAY_2016,
        billable_units=1, rate_multiplier=2, status='delivered'
    )
    create_notification(
        template=sample_template, created_at=IN_JUN_2016,
        billable_units=2, rate_multiplier=3, status='delivered'
    )
    create_letter_rate(crown=False, start_date=IN_MAY_2016, end_date=IN_JUN_2016)
    create_letter_rate(crown=False, start_date=IN_JUN_2016, rate=0.41)

    letter_template = create_template(service=sample_template.service, template_type=LETTER_TYPE)
    create_notification(template=letter_template, created_at=IN_MAY_2016, status='delivered', billable_units=1)
    create_notification(template=letter_template, created_at=IN_JUN_2016, status='delivered', billable_units=1)

    create_or_update_monthly_billing(service_id=sample_template.service_id, billing_month=IN_MAY_2016)
    create_or_update_monthly_billing(service_id=sample_template.service_id, billing_month=IN_JUN_2016)

    response = client.get(
        '/service/{}/billing/yearly-usage-summary?year=2016'.format(sample_template.service.id),
        headers=[create_authorization_header()]
    )
    assert response.status_code == 200

    resp_json = json.loads(response.get_data(as_text=True))
    assert len(resp_json) == 3

    _assert_dict_equals(resp_json[0], {
        'notification_type': SMS_TYPE,
        'billing_units': 8,
        'rate': 0.12,
        'letter_total': 0
    })

    _assert_dict_equals(resp_json[1], {
        'notification_type': EMAIL_TYPE,
        'billing_units': 0,
        'rate': 0,
        'letter_total': 0
    })
    _assert_dict_equals(resp_json[2], {
        'notification_type': LETTER_TYPE,
        'billing_units': 2,
        'rate': 0,
        'letter_total': 0.72
    })


def test_get_yearly_billing_usage_breakdown_returns_400_if_missing_year(client, sample_service):
    response = client.get(
        '/service/{}/billing/yearly-usage-summary'.format(sample_service.id),
        headers=[create_authorization_header()]
    )
    assert response.status_code == 400
    assert json.loads(response.get_data(as_text=True)) == {
        'message': 'No valid year provided', 'result': 'error'
    }


def test_get_yearly_usage_by_month_returns_400_if_missing_year(client, sample_service):
    response = client.get(
        '/service/{}/billing/monthly-usage'.format(sample_service.id),
        headers=[create_authorization_header()]
    )
    assert response.status_code == 400
    assert json.loads(response.get_data(as_text=True)) == {
        'message': 'No valid year provided', 'result': 'error'
    }


def test_get_yearly_usage_by_month_returns_empty_list_if_no_usage(client, sample_template):
    create_rate(start_date=IN_MAY_2016 - timedelta(days=1), value=0.12, notification_type=SMS_TYPE)
    response = client.get(
        '/service/{}/billing/monthly-usage?year=2016'.format(sample_template.service.id),
        headers=[create_authorization_header()]
    )
    assert response.status_code == 200

    results = json.loads(response.get_data(as_text=True))
    assert results == []


def test_get_yearly_usage_by_month_returns_correctly(client, sample_template):
    create_rate(start_date=IN_MAY_2016 - timedelta(days=1), value=0.12, notification_type=SMS_TYPE)
    create_notification(
        template=sample_template, created_at=IN_MAY_2016,
        billable_units=1, rate_multiplier=2, status='delivered'
    )
    create_notification(
        template=sample_template, created_at=IN_JUN_2016,
        billable_units=2, rate_multiplier=3, status='delivered'
    )

    create_or_update_monthly_billing(service_id=sample_template.service_id, billing_month=IN_MAY_2016)
    create_or_update_monthly_billing(service_id=sample_template.service_id, billing_month=IN_JUN_2016)

    response = client.get(
        '/service/{}/billing/monthly-usage?year=2016'.format(sample_template.service.id),
        headers=[create_authorization_header()]
    )

    assert response.status_code == 200

    resp_json = json.loads(response.get_data(as_text=True))
    _assert_dict_equals(resp_json[0], {
        'billing_units': 2,
        'month': 'May',
        'notification_type': SMS_TYPE,
        'rate': 0.12
    })
    _assert_dict_equals(resp_json[1], {
        'billing_units': 0,
        'month': 'May',
        'notification_type': LETTER_TYPE,
        'rate': 0
    })

    _assert_dict_equals(resp_json[2], {
        'billing_units': 6,
        'month': 'June',
        'notification_type': SMS_TYPE,
        'rate': 0.12
    })
    _assert_dict_equals(resp_json[3], {
        'billing_units': 0,
        'month': 'June',
        'notification_type': LETTER_TYPE,
        'rate': 0
    })


def test_transform_billing_for_month_returns_empty_if_no_monthly_totals(sample_service):
    create_monthly_billing_entry(
        service=sample_service,
        monthly_totals=[],
        start_date=APR_2016_MONTH_START,
        end_date=APR_2016_MONTH_END,
        notification_type=SMS_TYPE
    )

    transformed_billing_data = _transform_billing_for_month_sms(get_monthly_billing_by_notification_type(
        sample_service.id, APR_2016_MONTH_START, SMS_TYPE
    ))

    _assert_dict_equals(transformed_billing_data, {
        'notification_type': SMS_TYPE,
        'billing_units': 0,
        'month': 'April',
        'rate': 0,
    })


def test_transform_billing_for_month_formats_monthly_totals_correctly(sample_service):
    create_monthly_billing_entry(
        service=sample_service,
        monthly_totals=[{
            "billing_units": 12,
            "rate": 0.0158,
            "rate_multiplier": 5,
            "total_cost": 2.1804,
            "international": False
        }],
        start_date=APR_2016_MONTH_START,
        end_date=APR_2016_MONTH_END,
        notification_type=SMS_TYPE
    )

    transformed_billing_data = _transform_billing_for_month_sms(get_monthly_billing_by_notification_type(
        sample_service.id, APR_2016_MONTH_START, SMS_TYPE
    ))

    _assert_dict_equals(transformed_billing_data, {
        'notification_type': SMS_TYPE,
        'billing_units': 60,
        'month': 'April',
        'rate': 0.0158,
    })


def test_transform_billing_sums_billable_units(sample_service):
    create_monthly_billing_entry(
        service=sample_service,
        monthly_totals=[{
            'billing_units': 1321,
            'international': False,
            'month': 'May',
            'notification_type': SMS_TYPE,
            'rate': 0.12,
            'rate_multiplier': 1
        }, {
            'billing_units': 1,
            'international': False,
            'month': 'May',
            'notification_type': SMS_TYPE,
            'rate': 0.12,
            'rate_multiplier': 1
        }],
        start_date=APR_2016_MONTH_START,
        end_date=APR_2016_MONTH_END,
        notification_type=SMS_TYPE
    )

    transformed_billing_data = _transform_billing_for_month_sms(get_monthly_billing_by_notification_type(
        sample_service.id, APR_2016_MONTH_START, SMS_TYPE
    ))

    _assert_dict_equals(transformed_billing_data, {
        'notification_type': SMS_TYPE,
        'billing_units': 1322,
        'month': 'April',
        'rate': 0.12,
    })


def test_transform_billing_calculates_with_different_rate_multipliers(sample_service):
    create_monthly_billing_entry(
        service=sample_service,
        monthly_totals=[{
            'billing_units': 1321,
            'international': False,
            'month': 'May',
            'notification_type': SMS_TYPE,
            'rate': 0.12,
            'rate_multiplier': 1
        }, {
            'billing_units': 1,
            'international': False,
            'month': 'May',
            'notification_type': SMS_TYPE,
            'rate': 0.12,
            'rate_multiplier': 3
        }],
        start_date=APR_2016_MONTH_START,
        end_date=APR_2016_MONTH_END,
        notification_type=SMS_TYPE
    )

    transformed_billing_data = _transform_billing_for_month_sms(get_monthly_billing_by_notification_type(
        sample_service.id, APR_2016_MONTH_START, SMS_TYPE
    ))

    _assert_dict_equals(transformed_billing_data, {
        'notification_type': SMS_TYPE,
        'billing_units': 1324,
        'month': 'April',
        'rate': 0.12,
    })


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


def test_get_yearly_usage_by_monthly_from_ft_billing(client, notify_db_session):
    service = create_service()
    sms_template = create_template(service=service, template_type="sms")
    email_template = create_template(service=service, template_type="email")
    letter_template = create_template(service=service, template_type="letter")
    for month in range(1, 13):
        mon = str(month).zfill(2)
        days_in_month = {1: 32, 2: 30, 3: 32, 4: 31, 5: 32, 6: 31, 7: 32, 8: 32, 9: 31, 10: 32, 11: 31, 12: 32}
        for day in range(1, days_in_month[month]):
            d = str(day).zfill(2)
            create_ft_billing(bst_date='2016-{}-{}'.format(mon, d),
                              service=service,
                              template=sms_template,
                              notification_type='sms',
                              rate=0.162)
            create_ft_billing(bst_date='2016-{}-{}'.format(mon, d),
                              service=service,
                              template=email_template,
                              notification_type='email',
                              rate=0)
            create_ft_billing(bst_date='2016-{}-{}'.format(mon, d),
                              service=service,
                              template=letter_template,
                              notification_type='letter',
                              rate=0.33)

    response = client.get('service/{}/billing/ft-monthly-usage?year=2016'.format(service.id),
                          headers=[('Content-Type', 'application/json'), create_authorization_header()])

    json_resp = json.loads(response.get_data(as_text=True))

    assert json_resp["monthly_usage"][0] == {"month": "April",
                                             "service_id": str(service.id),
                                             "notifications_type": 'email',
                                             "notifications_sent": 30,
                                             "billable_units": 30,
                                             "rate": 0.0,
                                             "rate_multiplier": 1,
                                             "international": False,
                                             }
