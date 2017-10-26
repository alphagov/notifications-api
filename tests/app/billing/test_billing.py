from datetime import datetime, timedelta
import json

from app.billing.rest import _transform_billing_for_month
from app.dao.monthly_billing_dao import (
    create_or_update_monthly_billing,
    get_monthly_billing_by_notification_type,
)
from app.models import SMS_TYPE, EMAIL_TYPE
from tests.app.db import (
    create_notification,
    create_rate,
    create_monthly_billing_entry
)

from tests import create_authorization_header
from app.dao.annual_billing_dao import (dao_get_free_sms_fragment_limit_for_year,
                                        dao_create_or_update_annual_billing_for_year)
from app.models import AnnualBilling
import uuid

APR_2016_MONTH_START = datetime(2016, 3, 31, 23, 00, 00)
APR_2016_MONTH_END = datetime(2016, 4, 30, 22, 59, 59, 99999)

IN_MAY_2016 = datetime(2016, 5, 10, 23, 00, 00)
IN_JUN_2016 = datetime(2016, 6, 3, 23, 00, 00)


def _assert_dict_equals(actual, expected_dict):
    assert set(actual.keys()) == set(expected_dict.keys())
    assert set(actual.values()) == set(expected_dict.values())


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

    create_or_update_monthly_billing(service_id=sample_template.service_id, billing_month=IN_MAY_2016)
    create_or_update_monthly_billing(service_id=sample_template.service_id, billing_month=IN_JUN_2016)

    response = client.get(
        '/service/{}/billing/yearly-usage-summary?year=2016'.format(sample_template.service.id),
        headers=[create_authorization_header()]
    )
    assert response.status_code == 200

    resp_json = json.loads(response.get_data(as_text=True))
    assert len(resp_json) == 2

    _assert_dict_equals(resp_json[0], {
        'notification_type': SMS_TYPE,
        'billing_units': 8,
        'rate': 0.12
    })

    _assert_dict_equals(resp_json[1], {
        'notification_type': EMAIL_TYPE,
        'billing_units': 0,
        'rate': 0
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
        'billing_units': 6,
        'month': 'June',
        'notification_type': SMS_TYPE,
        'rate': 0.12
    })


def test_transform_billing_for_month_returns_empty_if_no_monthly_totals(sample_service):
    create_monthly_billing_entry(
        service=sample_service,
        monthly_totals=[],
        start_date=APR_2016_MONTH_START,
        end_date=APR_2016_MONTH_END,
        notification_type=SMS_TYPE
    )

    transformed_billing_data = _transform_billing_for_month(get_monthly_billing_by_notification_type(
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

    transformed_billing_data = _transform_billing_for_month(get_monthly_billing_by_notification_type(
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

    transformed_billing_data = _transform_billing_for_month(get_monthly_billing_by_notification_type(
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

    transformed_billing_data = _transform_billing_for_month(get_monthly_billing_by_notification_type(
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


def test_create_free_sms_fragment_limit(client, sample_service):

    data = {'financial_year_start': 2017, 'free_sms_fragment_limit': 250}
    response = client.post('service/{}/billing/free-sms-fragment-limit'.format(sample_service.id),
                           data=json.dumps(data),
                           headers=[('Content-Type', 'application/json'), create_authorization_header()])

    response_get = client.get(
        'service/{}/billing/free-sms-fragment-limit?financial_year_start=2017'.format(sample_service.id),
        headers=[('Content-Type', 'application/json'), create_authorization_header()])

    json_resp = json.loads(response_get.get_data(as_text=True))
    assert response.status_code == 201
    assert response_get.status_code == 200
    assert json_resp['data']['financial_year_start'] == 2017
    assert json_resp['data']['free_sms_fragment_limit'] == 250


def test_update_free_sms_fragment_limit(client, sample_service):

    data_old = {'financial_year_start': 2015, 'free_sms_fragment_limit': 1000}
    response = client.post('service/{}/billing/free-sms-fragment-limit'.format(sample_service.id),
                           data=json.dumps(data_old),
                           headers=[('Content-Type', 'application/json'), create_authorization_header()])

    data_new = {'financial_year_start': 2015, 'free_sms_fragment_limit': 9999}
    response = client.post('service/{}/billing/free-sms-fragment-limit'.format(sample_service.id),
                           data=json.dumps(data_new),
                           headers=[('Content-Type', 'application/json'), create_authorization_header()])

    response_get = client.get(
        'service/{}/billing/free-sms-fragment-limit?financial_year_start=2015'.format(sample_service.id),
        headers=[('Content-Type', 'application/json'), create_authorization_header()])

    json_resp = json.loads(response_get.get_data(as_text=True))

    assert response.status_code == 201
    assert response_get.status_code == 200
    assert json_resp['data']['financial_year_start'] == 2015
    assert json_resp['data']['free_sms_fragment_limit'] == 9999


def test_get_free_sms_fragment_limit_year_return_correct_data(client, sample_service):
    years = [2015, 2016, 2017]
    limits = [1000, 2000, 3000]

    for i in range(0, len(years)):
        annual_billing = {'financial_year_start': years[i], 'free_sms_fragment_limit': limits[i]}
        response = client.post('service/{}/billing/free-sms-fragment-limit'.format(sample_service.id),
                               data=json.dumps(annual_billing),
                               headers=[('Content-Type', 'application/json'), create_authorization_header()])

    for i in range(0, len(years)):
        response_get = client.get(
            'service/{}/billing/free-sms-fragment-limit?financial_year_start={}'.format(sample_service.id, years[i]),
            headers=[('Content-Type', 'application/json'), create_authorization_header()])
        json_resp = json.loads(response_get.get_data(as_text=True))
        assert response_get.status_code == 200
        assert json_resp['data']['free_sms_fragment_limit'] == limits[i]


def test_get_free_sms_fragment_limit_for_all_years(client, sample_service):
    years = [2015, 2016, 2017]
    limits = [1000, 2000, 3000]

    for i in range(0, len(years)):
        annual_billing = {'financial_year_start': years[i], 'free_sms_fragment_limit': limits[i]}
        response = client.post('service/{}/billing/free-sms-fragment-limit'.format(sample_service.id),
                               data=json.dumps(annual_billing),
                               headers=[('Content-Type', 'application/json'), create_authorization_header()])

    response_get = client.get(
        # Not specify a particular year to return all data for that service
        'service/{}/billing/free-sms-fragment-limit'.format(sample_service.id),
        headers=[('Content-Type', 'application/json'), create_authorization_header()])
    json_resp = json.loads(response_get.get_data(as_text=True))
    assert response_get.status_code == 200
    assert len(json_resp['data']) == 3
    print(json_resp)
    for i in [0, 1, 2]:
        assert json_resp['data'][i]['free_sms_fragment_limit'] == limits[i]
        assert json_resp['data'][i]['financial_year_start'] == years[i]


def test_get_free_sms_fragment_limit_no_year_data_return_404(client, sample_service):

    response_get = client.get(
        'service/{}/billing/free-sms-fragment-limit?financial_year_start={}'.format(sample_service.id, 1999),
        headers=[('Content-Type', 'application/json'), create_authorization_header()])
    json_resp = json.loads(response_get.get_data(as_text=True))

    assert response_get.status_code == 404


def test_get_free_sms_fragment_limit_unknown_service_id_return_404(client):

    response_get = client.get(
        'service/{}/billing/free-sms-fragment-limit'.format(uuid.uuid4()),
        headers=[('Content-Type', 'application/json'), create_authorization_header()])
    json_resp = json.loads(response_get.get_data(as_text=True))
    assert response_get.status_code == 404
