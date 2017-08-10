from datetime import datetime, timedelta
from freezegun import freeze_time
from freezegun.api import FakeDatetime

from app import db
from app.dao.monthly_billing_dao import (
    create_or_update_monthly_billing_sms,
    get_monthly_billing_entry,
    get_monthly_billing_sms,
    get_service_ids_that_need_sms_billing_populated
)
from app.models import MonthlyBilling, SMS_TYPE
from tests.app.db import create_notification, create_rate, create_service, create_template


def create_sample_monthly_billing_entry(
    service_id,
    monthly_totals,
    start_date,
    end_date,
    notification_type=SMS_TYPE
):
    entry = MonthlyBilling(
        service_id=service_id,
        notification_type=notification_type,
        monthly_totals=monthly_totals,
        start_date=start_date,
        end_date=end_date
    )
    db.session.add(entry)
    db.session.commit()

    return entry


def test_add_monthly_billing(sample_template):
    jan = datetime(2017, 1, 1)
    feb = datetime(2017, 2, 15)
    create_rate(start_date=jan, value=0.0158, notification_type=SMS_TYPE)
    create_rate(start_date=datetime(2017, 3, 31, 23, 00, 00), value=0.123, notification_type=SMS_TYPE)
    create_notification(template=sample_template, created_at=jan, billable_units=1, status='delivered')
    create_notification(template=sample_template, created_at=feb, billable_units=2, status='delivered')

    create_or_update_monthly_billing_sms(service_id=sample_template.service_id,
                                         billing_month=jan)
    create_or_update_monthly_billing_sms(service_id=sample_template.service_id,
                                         billing_month=feb)
    monthly_billing = MonthlyBilling.query.all()
    assert len(monthly_billing) == 2
    assert monthly_billing[0].start_date == datetime(2017, 1, 1)
    assert monthly_billing[1].start_date == datetime(2017, 2, 1)

    january = get_monthly_billing_sms(service_id=sample_template.service_id, billing_month=jan)
    expected_jan = {"billing_units": 1,
                    "rate_multiplier": 1,
                    "international": False,
                    "rate": 0.0158,
                    "total_cost": 1 * 0.0158}
    assert_monthly_billing(january, sample_template.service_id, 1, expected_jan,
                           start_date=datetime(2017, 1, 1), end_date=datetime(2017, 1, 31))

    february = get_monthly_billing_sms(service_id=sample_template.service_id, billing_month=feb)
    expected_feb = {"billing_units": 2,
                    "rate_multiplier": 1,
                    "international": False,
                    "rate": 0.0158,
                    "total_cost": 2 * 0.0158}
    assert_monthly_billing(february, sample_template.service_id, 1, expected_feb,
                           start_date=datetime(2017, 2, 1), end_date=datetime(2017, 2, 28))


def test_add_monthly_billing_multiple_rates_in_a_month(sample_template):
    rate_1 = datetime(2016, 12, 1)
    rate_2 = datetime(2017, 1, 15)
    create_rate(start_date=rate_1, value=0.0158, notification_type=SMS_TYPE)
    create_rate(start_date=rate_2, value=0.0124, notification_type=SMS_TYPE)

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
    assert monthly_billing[0].start_date == datetime(2017, 1, 1)

    january = get_monthly_billing_sms(service_id=sample_template.service_id, billing_month=rate_2)
    first_row = {"billing_units": 2,
                 "rate_multiplier": 1,
                 "international": False,
                 "rate": 0.0158,
                 "total_cost": 3 * 0.0158}
    assert_monthly_billing(january, sample_template.service_id, 2, first_row,
                           start_date=datetime(2017, 1, 1), end_date=datetime(2017, 1, 1))
    second_row = {"billing_units": 6,
                  "rate_multiplier": 1,
                  "international": False,
                  "rate": 0.0124,
                  "total_cost": 1 * 0.0124}
    assert sorted(january.monthly_totals[1]) == sorted(second_row)


def test_update_monthly_billing_overwrites_old_totals(sample_template):
    july = datetime(2017, 7, 1)
    create_rate(july, 0.123, SMS_TYPE)
    create_notification(template=sample_template, created_at=datetime(2017, 7, 2), billable_units=1, status='delivered')
    with freeze_time('2017-07-20 02:30:00'):
        create_or_update_monthly_billing_sms(sample_template.service_id, july)
    first_update = get_monthly_billing_sms(sample_template.service_id, july)
    expected = {"billing_units": 1,
                "rate_multiplier": 1,
                "international": False,
                "rate": 0.123,
                "total_cost": 1 * 0.123}
    assert_monthly_billing(first_update, sample_template.service_id, 1, expected,
                           start_date=datetime(2017, 6, 30, 23), end_date=datetime(2017, 7, 31, 23, 59, 59, 99999))
    first_updated_at = first_update.updated_at
    with freeze_time('2017-07-20 03:30:00'):
        create_notification(template=sample_template, created_at=datetime(2017, 7, 5), billable_units=2,
                            status='delivered')

        create_or_update_monthly_billing_sms(sample_template.service_id, july)
    second_update = get_monthly_billing_sms(sample_template.service_id, july)
    expected_update = {"billing_units": 3,
                       "rate_multiplier": 1,
                       "international": False,
                       "rate": 0.123,
                       "total_cost": 3 * 0.123}
    assert_monthly_billing(second_update, sample_template.service_id, 1, expected_update,
                           start_date=datetime(2017, 6, 30, 23), end_date=datetime(2017, 7, 31, 23, 59, 59, 99999))
    assert second_update.updated_at == FakeDatetime(2017, 7, 20, 3, 30)
    assert first_updated_at != second_update.updated_at


def assert_monthly_billing(monthly_billing, service_id, expected_len, first_row, start_date, end_date):
    assert monthly_billing.service_id == service_id
    assert len(monthly_billing.monthly_totals) == expected_len
    assert sorted(monthly_billing.monthly_totals[0]) == sorted(first_row)


def test_get_service_id(notify_db_session):
    service_1 = create_service(service_name="Service One")
    template_1 = create_template(service=service_1)
    service_2 = create_service(service_name="Service Two")
    template_2 = create_template(service=service_2)
    create_notification(template=template_1, created_at=datetime(2017, 6, 30, 13, 30), status='delivered')
    create_notification(template=template_1, created_at=datetime(2017, 7, 1, 14, 30), status='delivered')
    create_notification(template=template_2, created_at=datetime(2017, 7, 15, 13, 30))
    create_notification(template=template_2, created_at=datetime(2017, 7, 31, 13, 30))
    services = get_service_ids_that_need_sms_billing_populated(start_date=datetime(2017, 7, 1),
                                                               end_date=datetime(2017, 7, 16))
    expected_services = [service_1.id, service_2.id]
    assert sorted([x.service_id for x in services]) == sorted(expected_services)


def test_get_monthly_billing_entry_filters_by_service(notify_db, notify_db_session):
    service_1 = create_service(service_name="Service One")
    service_2 = create_service(service_name="Service Two")
    now = datetime.utcnow()

    create_sample_monthly_billing_entry(
        service_id=service_1.id,
        monthly_totals=[],
        start_date=now,
        end_date=now + timedelta(days=30)
    )

    create_sample_monthly_billing_entry(
        service_id=service_2.id,
        monthly_totals=[],
        start_date=now,
        end_date=now + timedelta(days=30)
    )

    entry = get_monthly_billing_entry(service_2.id, now, SMS_TYPE)

    assert entry.start_date == now
    assert entry.service_id == service_2.id
