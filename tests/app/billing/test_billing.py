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
        'billing_units': 1,
        'international': False,
        'month': 'May',
        'notification_type': SMS_TYPE,
        'rate': 0.12,
        'rate_multiplier': 2
    })

    _assert_dict_equals(resp_json[1], {
        'billing_units': 2,
        'international': False,
        'month': 'June',
        'notification_type': SMS_TYPE,
        'rate': 0.12,
        'rate_multiplier': 3
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
        'international': False,
        'rate_multiplier': 0,
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
        'billing_units': 12,
        'month': 'April',
        'international': False,
        'rate_multiplier': 5,
        'rate': 0.0158,
    })
