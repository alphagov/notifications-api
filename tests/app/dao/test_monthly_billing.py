from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from freezegun import freeze_time
from functools import partial

from app.dao.monthly_billing_dao import (
    create_or_update_monthly_billing,
    get_monthly_billing_entry,
    get_monthly_billing_by_notification_type,
    get_service_ids_that_need_billing_populated,
    get_billing_data_for_financial_year
)
from app.models import MonthlyBilling, SMS_TYPE, EMAIL_TYPE
from tests.app.db import (
    create_notification,
    create_rate,
    create_service,
    create_template,
    create_monthly_billing_entry
)

FEB_2016_MONTH_START = datetime(2016, 2, 1)
FEB_2016_MONTH_END = datetime(2016, 2, 29, 23, 59, 59, 99999)

MAR_2016_MONTH_START = datetime(2016, 3, 1)
MAR_2016_MONTH_END = datetime(2016, 3, 31, 22, 59, 59, 99999)

APR_2016_MONTH_START = datetime(2016, 3, 31, 23, 00, 00)
APR_2016_MONTH_END = datetime(2016, 4, 30, 22, 59, 59, 99999)

MAY_2016_MONTH_START = datetime(2016, 5, 31, 23, 00, 00)
MAY_2016_MONTH_END = MAY_2016_MONTH_START + relativedelta(months=1, seconds=-1)

APR_2017_MONTH_START = datetime(2017, 3, 31, 23, 00, 00)
APR_2017_MONTH_END = datetime(2017, 4, 30, 23, 59, 59, 99999)

JAN_2017_MONTH_START = datetime(2017, 1, 1)
JAN_2017_MONTH_END = datetime(2017, 1, 31, 23, 59, 59, 99999)

FEB_2017 = datetime(2017, 2, 15)
APR_2016 = datetime(2016, 4, 10)

NO_BILLING_DATA = {
    "billing_units": 0,
    "rate_multiplier": 1,
    "international": False,
    "rate": 0,
    "total_cost": 0
}


def _assert_monthly_billing(monthly_billing, service_id, notification_type, month_start, month_end):
    assert monthly_billing.service_id == service_id
    assert monthly_billing.notification_type == notification_type
    assert monthly_billing.start_date == month_start
    assert monthly_billing.end_date == month_end


def _assert_monthly_billing_totals(monthly_billing_totals, expected_dict):
    assert sorted(monthly_billing_totals.keys()) == sorted(expected_dict.keys())
    assert sorted(monthly_billing_totals.values()) == sorted(expected_dict.values())


def test_get_monthly_billing_by_notification_type_returns_correct_totals(notify_db, notify_db_session):
    service = create_service(service_name="Service One")

    create_monthly_billing_entry(
        service=service,
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

    monthly_billing_data = get_monthly_billing_by_notification_type(service.id, APR_2016, SMS_TYPE)

    _assert_monthly_billing(
        monthly_billing_data, service.id, 'sms', APR_2016_MONTH_START, APR_2016_MONTH_END
    )
    _assert_monthly_billing_totals(monthly_billing_data.monthly_totals[0], {
        "billing_units": 12,
        "rate_multiplier": 5,
        "international": False,
        "rate": 0.0158,
        "total_cost": 2.1804
    })


def test_get_monthly_billing_by_notification_type_filters_by_type(notify_db, notify_db_session):
    service = create_service(service_name="Service One")

    create_monthly_billing_entry(
        service=service,
        monthly_totals=[{
            "billing_units": 138,
            "rate": 0.0158,
            "rate_multiplier": 1,
            "total_cost": 2.1804,
            "international": None
        }],
        start_date=APR_2016_MONTH_START,
        end_date=APR_2016_MONTH_END,
        notification_type=SMS_TYPE
    )

    create_monthly_billing_entry(
        service=service,
        monthly_totals=[],
        start_date=APR_2016_MONTH_START,
        end_date=APR_2016_MONTH_END,
        notification_type=EMAIL_TYPE
    )

    monthly_billing_data = get_monthly_billing_by_notification_type(service.id, APR_2016, EMAIL_TYPE)

    _assert_monthly_billing(
        monthly_billing_data, service.id, 'email', APR_2016_MONTH_START, APR_2016_MONTH_END
    )
    assert monthly_billing_data.monthly_totals == []


def test_get_monthly_billing_by_notification_type_normalises_start_date(notify_db, notify_db_session):
    service = create_service(service_name="Service One")

    create_monthly_billing_entry(
        service=service,
        monthly_totals=[{
            "billing_units": 321,
            "rate": 0.0158,
            "rate_multiplier": 1,
            "total_cost": 2.1804,
            "international": None
        }],
        start_date=APR_2016_MONTH_START,
        end_date=APR_2016_MONTH_END,
        notification_type=SMS_TYPE
    )

    monthly_billing_data = get_monthly_billing_by_notification_type(service.id, APR_2016 + timedelta(days=5), SMS_TYPE)

    assert monthly_billing_data.start_date == APR_2016_MONTH_START
    assert monthly_billing_data.monthly_totals[0]['billing_units'] == 321


def test_add_monthly_billing_for_single_month_populates_correctly(
    sample_template, sample_email_template
):
    create_rate(start_date=JAN_2017_MONTH_START, value=0.0158, notification_type=SMS_TYPE)
    create_notification(
        template=sample_template, created_at=JAN_2017_MONTH_START,
        billable_units=1, rate_multiplier=2, status='delivered'
    )

    create_or_update_monthly_billing(
        service_id=sample_template.service_id,
        billing_month=JAN_2017_MONTH_START
    )

    monthly_billing = MonthlyBilling.query.order_by(MonthlyBilling.notification_type).all()

    assert len(monthly_billing) == 3
    _assert_monthly_billing(
        monthly_billing[0], sample_template.service.id, 'email', JAN_2017_MONTH_START, JAN_2017_MONTH_END
    )
    assert monthly_billing[0].monthly_totals == []

    _assert_monthly_billing(
        monthly_billing[1], sample_template.service.id, 'sms', JAN_2017_MONTH_START, JAN_2017_MONTH_END
    )
    _assert_monthly_billing_totals(monthly_billing[1].monthly_totals[0], {
        "billing_units": 1,
        "rate_multiplier": 2,
        "international": False,
        "rate": 0.0158,
        "total_cost": 1 * 2 * 0.0158
    })

    _assert_monthly_billing(
        monthly_billing[2], sample_template.service.id, 'letter', JAN_2017_MONTH_START, JAN_2017_MONTH_END
    )
    assert monthly_billing[2].monthly_totals == []


def test_add_monthly_billing_for_multiple_months_populate_correctly(
    sample_template, sample_email_template
):
    create_rate(start_date=FEB_2016_MONTH_START - timedelta(days=1), value=0.12, notification_type=SMS_TYPE)
    create_notification(
        template=sample_template, created_at=FEB_2016_MONTH_START,
        billable_units=1, rate_multiplier=2, status='delivered'
    )
    create_notification(
        template=sample_template, created_at=MAR_2016_MONTH_START,
        billable_units=2, rate_multiplier=3, status='delivered'
    )

    create_or_update_monthly_billing(service_id=sample_template.service_id, billing_month=FEB_2016_MONTH_START)
    create_or_update_monthly_billing(service_id=sample_template.service_id, billing_month=MAR_2016_MONTH_START)

    monthly_billing = MonthlyBilling.query.order_by(
        MonthlyBilling.notification_type,
        MonthlyBilling.start_date
    ).all()

    assert len(monthly_billing) == 6
    _assert_monthly_billing(
        monthly_billing[0], sample_template.service.id, 'email', FEB_2016_MONTH_START, FEB_2016_MONTH_END
    )
    assert monthly_billing[0].monthly_totals == []

    _assert_monthly_billing(
        monthly_billing[1], sample_template.service.id, 'email', MAR_2016_MONTH_START, MAR_2016_MONTH_END
    )
    assert monthly_billing[1].monthly_totals == []

    _assert_monthly_billing(
        monthly_billing[2], sample_template.service.id, 'sms', FEB_2016_MONTH_START, FEB_2016_MONTH_END
    )
    _assert_monthly_billing_totals(monthly_billing[2].monthly_totals[0], {
        "billing_units": 1,
        "rate_multiplier": 2,
        "international": False,
        "rate": 0.12,
        "total_cost": 0.24
    })

    _assert_monthly_billing(
        monthly_billing[3], sample_template.service.id, 'sms', MAR_2016_MONTH_START, MAR_2016_MONTH_END
    )
    _assert_monthly_billing_totals(monthly_billing[3].monthly_totals[0], {
        "billing_units": 2,
        "rate_multiplier": 3,
        "international": False,
        "rate": 0.12,
        "total_cost": 0.72
    })

    _assert_monthly_billing(
        monthly_billing[4], sample_template.service.id, 'letter', FEB_2016_MONTH_START, FEB_2016_MONTH_END
    )
    assert monthly_billing[4].monthly_totals == []

    _assert_monthly_billing(
        monthly_billing[5], sample_template.service.id, 'letter', MAR_2016_MONTH_START, MAR_2016_MONTH_END
    )
    assert monthly_billing[5].monthly_totals == []


def test_add_monthly_billing_with_multiple_rates_populate_correctly(
    sample_template
):
    create_rate(start_date=JAN_2017_MONTH_START, value=0.0158, notification_type=SMS_TYPE)
    create_rate(start_date=JAN_2017_MONTH_START + timedelta(days=5), value=0.123, notification_type=SMS_TYPE)
    create_notification(template=sample_template, created_at=JAN_2017_MONTH_START, billable_units=1, status='delivered')
    create_notification(
        template=sample_template, created_at=JAN_2017_MONTH_START + timedelta(days=6),
        billable_units=2, status='delivered'
    )

    create_or_update_monthly_billing(service_id=sample_template.service_id, billing_month=JAN_2017_MONTH_START)

    monthly_billing = MonthlyBilling.query.order_by(MonthlyBilling.notification_type).all()

    assert len(monthly_billing) == 3
    _assert_monthly_billing(
        monthly_billing[0], sample_template.service.id, 'email', JAN_2017_MONTH_START, JAN_2017_MONTH_END
    )
    assert monthly_billing[0].monthly_totals == []

    _assert_monthly_billing(
        monthly_billing[1], sample_template.service.id, 'sms', JAN_2017_MONTH_START, JAN_2017_MONTH_END
    )
    _assert_monthly_billing_totals(monthly_billing[1].monthly_totals[0], {
        "billing_units": 1,
        "rate_multiplier": 1,
        "international": False,
        "rate": 0.0158,
        "total_cost": 0.0158
    })
    _assert_monthly_billing_totals(monthly_billing[1].monthly_totals[1], {
        "billing_units": 2,
        "rate_multiplier": 1,
        "international": False,
        "rate": 0.123,
        "total_cost": 0.246
    })

    _assert_monthly_billing(
        monthly_billing[2], sample_template.service.id, 'letter', JAN_2017_MONTH_START, JAN_2017_MONTH_END
    )
    assert monthly_billing[0].monthly_totals == []


def test_update_monthly_billing_overwrites_old_totals(sample_template):
    create_rate(APR_2016_MONTH_START, 0.123, SMS_TYPE)
    create_notification(template=sample_template, created_at=APR_2016_MONTH_START, billable_units=1, status='delivered')

    create_or_update_monthly_billing(sample_template.service_id, APR_2016_MONTH_END)
    first_update = get_monthly_billing_by_notification_type(sample_template.service_id, APR_2016_MONTH_START, SMS_TYPE)

    _assert_monthly_billing(
        first_update, sample_template.service.id, 'sms', APR_2016_MONTH_START, APR_2016_MONTH_END
    )
    _assert_monthly_billing_totals(first_update.monthly_totals[0], {
        "billing_units": 1,
        "rate_multiplier": 1,
        "international": False,
        "rate": 0.123,
        "total_cost": 0.123
    })

    first_updated_at = first_update.updated_at

    with freeze_time(APR_2016_MONTH_START + timedelta(days=3)):
        create_notification(template=sample_template, billable_units=2, status='delivered')
        create_or_update_monthly_billing(sample_template.service_id, APR_2016_MONTH_END)

    second_update = get_monthly_billing_by_notification_type(sample_template.service_id, APR_2016_MONTH_START, SMS_TYPE)

    _assert_monthly_billing_totals(second_update.monthly_totals[0], {
        "billing_units": 3,
        "rate_multiplier": 1,
        "international": False,
        "rate": 0.123,
        "total_cost": 0.369
    })

    assert second_update.updated_at == APR_2016_MONTH_START + timedelta(days=3)
    assert first_updated_at != second_update.updated_at


def test_get_service_ids_that_need_billing_populated_return_correctly(notify_db_session):
    service_1 = create_service(service_name="Service One")
    template_1 = create_template(service=service_1)
    service_2 = create_service(service_name="Service Two")
    template_2 = create_template(service=service_2)
    create_notification(template=template_1, created_at=datetime(2017, 6, 30, 13, 30), status='delivered')
    create_notification(template=template_1, created_at=datetime(2017, 7, 1, 14, 30), status='delivered')
    create_notification(template=template_2, created_at=datetime(2017, 7, 15, 13, 30))
    create_notification(template=template_2, created_at=datetime(2017, 7, 31, 13, 30))
    services = get_service_ids_that_need_billing_populated(
        start_date=datetime(2017, 7, 1), end_date=datetime(2017, 7, 16)
    )
    expected_services = [service_1.id, service_2.id]
    assert sorted([x.service_id for x in services]) == sorted(expected_services)


def test_get_monthly_billing_entry_filters_by_service(notify_db, notify_db_session):
    service_1 = create_service(service_name="Service One")
    service_2 = create_service(service_name="Service Two")
    now = datetime.utcnow()

    create_monthly_billing_entry(
        service=service_1,
        monthly_totals=[],
        start_date=now,
        end_date=now + timedelta(days=30),
        notification_type=SMS_TYPE
    )

    create_monthly_billing_entry(
        service=service_2,
        monthly_totals=[],
        start_date=now,
        end_date=now + timedelta(days=30),
        notification_type=SMS_TYPE
    )

    entry = get_monthly_billing_entry(service_2.id, now, SMS_TYPE)

    assert entry.start_date == now
    assert entry.service_id == service_2.id


def test_get_yearly_billing_data_for_year_returns_within_year_only(
    sample_template
):
    monthly_billing_entry = partial(
        create_monthly_billing_entry, service=sample_template.service, notification_type=SMS_TYPE
    )
    monthly_billing_entry(start_date=FEB_2016_MONTH_START, end_date=FEB_2016_MONTH_END)
    monthly_billing_entry(
        monthly_totals=[{
            "billing_units": 138,
            "rate": 0.0158,
            "rate_multiplier": 1,
            "total_cost": 2.1804,
            "international": None
        }],
        start_date=APR_2016_MONTH_START,
        end_date=APR_2016_MONTH_END,
        notification_type=SMS_TYPE
    )
    monthly_billing_entry(start_date=APR_2017_MONTH_START, end_date=APR_2017_MONTH_END)

    billing_data = get_billing_data_for_financial_year(sample_template.service.id, 2016, [SMS_TYPE])

    assert len(billing_data) == 1
    assert billing_data[0].monthly_totals[0]['billing_units'] == 138


def test_get_yearly_billing_data_for_year_returns_multiple_notification_types(sample_template):
    monthly_billing_entry = partial(
        create_monthly_billing_entry, service=sample_template.service,
        start_date=APR_2016_MONTH_START, end_date=APR_2016_MONTH_END
    )

    monthly_billing_entry(
        notification_type=SMS_TYPE, monthly_totals=[]
    )
    monthly_billing_entry(
        notification_type=EMAIL_TYPE,
        monthly_totals=[{
            "billing_units": 2,
            "rate": 1.3,
            "rate_multiplier": 3,
            "total_cost": 2.1804,
            "international": False
        }]
    )

    billing_data = get_billing_data_for_financial_year(
        service_id=sample_template.service.id,
        year=2016,
        notification_types=[SMS_TYPE, EMAIL_TYPE]
    )

    assert len(billing_data) == 2

    assert billing_data[0].notification_type == EMAIL_TYPE
    assert billing_data[0].monthly_totals[0]['billing_units'] == 2
    assert billing_data[1].notification_type == SMS_TYPE


@freeze_time("2016-04-21 11:00:00")
def test_get_yearly_billing_data_for_year_includes_current_day_totals(sample_template):
    create_rate(start_date=FEB_2016_MONTH_START, value=0.0158, notification_type=SMS_TYPE)

    create_monthly_billing_entry(
        service=sample_template.service,
        start_date=APR_2016_MONTH_START,
        end_date=APR_2016_MONTH_END,
        notification_type=SMS_TYPE
    )

    billing_data = get_billing_data_for_financial_year(
        service_id=sample_template.service.id,
        year=2016,
        notification_types=[SMS_TYPE]
    )

    assert len(billing_data) == 1
    assert billing_data[0].notification_type == SMS_TYPE
    assert billing_data[0].monthly_totals == []

    create_notification(
        template=sample_template,
        created_at=datetime.utcnow(),
        sent_at=datetime.utcnow(),
        status='sending',
        billable_units=3
    )

    billing_data = get_billing_data_for_financial_year(
        service_id=sample_template.service.id,
        year=2016,
        notification_types=[SMS_TYPE]
    )

    assert billing_data[0].monthly_totals[0]['billing_units'] == 3
