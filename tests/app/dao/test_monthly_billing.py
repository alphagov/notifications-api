from datetime import datetime

from app.dao.monthly_billing_dao import create_or_update_monthly_billing_sms, get_monthly_billing_sms
from app.models import MonthlyBilling
from tests.app.db import create_notification, create_rate


def test_add_monthly_billing(sample_template):
    jan = datetime(2017, 1, 1)
    feb = datetime(2017, 2, 15)
    create_rate(start_date=jan, value=0.0158, notification_type='sms')
    create_notification(template=sample_template, created_at=jan, billable_units=1, status='delivered')
    create_notification(template=sample_template, created_at=feb, billable_units=2, status='delivered')

    create_or_update_monthly_billing_sms(service_id=sample_template.service_id,
                                         billing_month=jan)
    create_or_update_monthly_billing_sms(service_id=sample_template.service_id,
                                         billing_month=feb)
    monthly_billing = MonthlyBilling.query.all()
    assert len(monthly_billing) == 2
    assert monthly_billing[0].month == 'January'
    assert monthly_billing[1].month == 'February'

    january = get_monthly_billing_sms(service_id=sample_template.service_id, billing_month=jan)
    expected_jan = {"billing_units": 1,
                    "rate_multiplier": 1,
                    "international": False,
                    "rate": 0.0158,
                    "total_cost": 1 * 0.0158}
    assert_monthly_billing(january, 2017, "January", sample_template.service_id, 1, expected_jan)

    february = get_monthly_billing_sms(service_id=sample_template.service_id, billing_month=feb)
    expected_feb = {"billing_units": 2,
                    "rate_multiplier": 1,
                    "international": False,
                    "rate": 0.0158,
                    "total_cost": 2 * 0.0158}
    assert_monthly_billing(february, 2017, "February", sample_template.service_id, 1, expected_feb)


def test_add_monthly_billing_multiple_rates_in_a_month(sample_template):
    rate_1 = datetime(2016, 12, 1)
    rate_2 = datetime(2017, 1, 15)
    create_rate(start_date=rate_1, value=0.0158, notification_type='sms')
    create_rate(start_date=rate_2, value=0.0124, notification_type='sms')

    create_notification(template=sample_template, created_at=datetime(2017, 1, 1), billable_units=1, status='delivered')
    create_notification(template=sample_template, created_at=datetime(2017, 1, 14, 23, 59), billable_units=1,
                        status='delivered')

    create_notification(template=sample_template, created_at=datetime(2017, 1, 15), billable_units=2,
                        status='delivered')
    create_notification(template=sample_template, created_at=datetime(2017, 1, 17, 13, 30, 57), billable_units=4,
                        status='delivered')

    create_or_update_monthly_billing_sms(service_id=sample_template.service_id,
                                         billing_month=rate_2)
    monthly_billing = MonthlyBilling.query.all()
    assert len(monthly_billing) == 1
    assert monthly_billing[0].month == 'January'

    january = get_monthly_billing_sms(service_id=sample_template.service_id, billing_month=rate_2)
    first_row = {"billing_units": 2,
                 "rate_multiplier": 1,
                 "international": False,
                 "rate": 0.0158,
                 "total_cost": 3 * 0.0158}
    assert_monthly_billing(january, 2017, "January", sample_template.service_id, 2, first_row)
    second_row = {"billing_units": 6,
                  "rate_multiplier": 1,
                  "international": False,
                  "rate": 0.0124,
                  "total_cost": 1 * 0.0124}
    assert sorted(january.monthly_totals[1]) == sorted(second_row)


def test_update_monthly_billing_overwrites_old_totals(sample_template):
    july = datetime(2017, 7, 1)
    create_rate(july, 0.123, 'sms')
    create_notification(template=sample_template, created_at=datetime(2017, 7, 2), billable_units=1, status='delivered')

    create_or_update_monthly_billing_sms(sample_template.service_id, july)
    first_update = get_monthly_billing_sms(sample_template.service_id, july)
    expected = {"billing_units": 1,
                "rate_multiplier": 1,
                "international": False,
                "rate": 0.123,
                "total_cost": 1 * 0.123}
    assert_monthly_billing(first_update, 2017, "July", sample_template.service_id, 1, expected)

    create_notification(template=sample_template, created_at=datetime(2017, 7, 5), billable_units=2, status='delivered')
    create_or_update_monthly_billing_sms(sample_template.service_id, july)
    second_update = get_monthly_billing_sms(sample_template.service_id, july)
    expected_update = {"billing_units": 3,
                       "rate_multiplier": 1,
                       "international": False,
                       "rate": 0.123,
                       "total_cost": 3 * 0.123}
    assert_monthly_billing(second_update, 2017, "July", sample_template.service_id, 1, expected_update)


def assert_monthly_billing(monthly_billing, year, month, service_id, expected_len, first_row):
    assert monthly_billing.year == year
    assert monthly_billing.month == month
    assert monthly_billing.service_id == service_id
    assert len(monthly_billing.monthly_totals) == expected_len
    assert sorted(monthly_billing.monthly_totals[0]) == sorted(first_row)
