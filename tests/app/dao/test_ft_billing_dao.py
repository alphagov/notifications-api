from calendar import monthrange
from decimal import Decimal

from datetime import datetime, timedelta
from freezegun import freeze_time

import pytest

from notifications_utils.timezones import convert_utc_to_bst

from app import db
from app.dao.fact_billing_dao import (
    delete_billing_data_for_service_for_day,
    fetch_billing_data_for_day,
    fetch_billing_totals_for_year,
    fetch_monthly_billing_for_year,
    get_rate,
    get_rates_for_billing,
)
from app.models import (
    FactBilling,
    Notification,
    NOTIFICATION_STATUS_TYPES,
)
from tests.app.db import (
    create_ft_billing,
    create_service,
    create_template,
    create_notification,
    create_rate,
)


def set_up_yearly_data():
    service = create_service()
    sms_template = create_template(service=service, template_type="sms")
    email_template = create_template(service=service, template_type="email")
    letter_template = create_template(service=service, template_type="letter")
    for year in (2016, 2017):
        for month in range(1, 13):
            mon = str(month).zfill(2)
            for day in range(1, monthrange(year, month)[1] + 1):
                d = str(day).zfill(2)
                create_ft_billing(bst_date='{}-{}-{}'.format(year, mon, d),
                                  service=service,
                                  template=sms_template,
                                  notification_type='sms',
                                  rate=0.162)
                create_ft_billing(bst_date='{}-{}-{}'.format(year, mon, d),
                                  service=service,
                                  template=email_template,
                                  notification_type='email',
                                  rate=0)
                create_ft_billing(bst_date='{}-{}-{}'.format(year, mon, d),
                                  service=service,
                                  template=letter_template,
                                  notification_type='letter',
                                  rate=0.33,
                                  postage='second')
                create_ft_billing(bst_date='{}-{}-{}'.format(year, mon, d),
                                  service=service,
                                  template=letter_template,
                                  notification_type='letter',
                                  rate=0.30,
                                  postage='second')
    return service


def test_fetch_billing_data_for_today_includes_data_with_the_right_status(notify_db_session):
    service = create_service()
    template = create_template(service=service, template_type="email")
    for status in ['created', 'technical-failure']:
        create_notification(template=template, status=status)

    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(today)
    assert results == []
    for status in ['delivered', 'sending', 'temporary-failure']:
        create_notification(template=template, status=status)
    results = fetch_billing_data_for_day(today)
    assert len(results) == 1
    assert results[0].notifications_sent == 3


def test_fetch_billing_data_for_today_includes_data_with_the_right_key_type(notify_db_session):
    service = create_service()
    template = create_template(service=service, template_type="email")
    for key_type in ['normal', 'test', 'team']:
        create_notification(template=template, status='delivered', key_type=key_type)

    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(today)
    assert len(results) == 1
    assert results[0].notifications_sent == 2


def test_fetch_billing_data_for_today_includes_data_with_the_right_date(notify_db_session):
    process_day = datetime(2018, 4, 1, 13, 30, 00)
    service = create_service()
    template = create_template(service=service, template_type="email")
    create_notification(template=template, status='delivered', created_at=process_day)
    create_notification(template=template, status='delivered', created_at=datetime(2018, 3, 31, 23, 23, 23))

    create_notification(template=template, status='delivered', created_at=datetime(2018, 3, 31, 20, 23, 23))
    create_notification(template=template, status='sending', created_at=process_day + timedelta(days=1))

    day_under_test = convert_utc_to_bst(process_day)
    results = fetch_billing_data_for_day(day_under_test)
    assert len(results) == 1
    assert results[0].notifications_sent == 2


def test_fetch_billing_data_for_day_is_grouped_by_template_and_notification_type(notify_db_session):
    service = create_service()
    email_template = create_template(service=service, template_type="email")
    sms_template = create_template(service=service, template_type="sms")
    create_notification(template=email_template, status='delivered')
    create_notification(template=sms_template, status='delivered')

    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(today)
    assert len(results) == 2
    assert results[0].notifications_sent == 1
    assert results[1].notifications_sent == 1


def test_fetch_billing_data_for_day_is_grouped_by_service(notify_db_session):
    service_1 = create_service()
    service_2 = create_service(service_name='Service 2')
    email_template = create_template(service=service_1)
    sms_template = create_template(service=service_2)
    create_notification(template=email_template, status='delivered')
    create_notification(template=sms_template, status='delivered')

    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(today)
    assert len(results) == 2
    assert results[0].notifications_sent == 1
    assert results[1].notifications_sent == 1


def test_fetch_billing_data_for_day_is_grouped_by_provider(notify_db_session):
    service = create_service()
    template = create_template(service=service)
    create_notification(template=template, status='delivered', sent_by='mmg')
    create_notification(template=template, status='delivered', sent_by='firetext')

    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(today)
    assert len(results) == 2
    assert results[0].notifications_sent == 1
    assert results[1].notifications_sent == 1


def test_fetch_billing_data_for_day_is_grouped_by_rate_mulitplier(notify_db_session):
    service = create_service()
    template = create_template(service=service)
    create_notification(template=template, status='delivered', rate_multiplier=1)
    create_notification(template=template, status='delivered', rate_multiplier=2)

    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(today)
    assert len(results) == 2
    assert results[0].notifications_sent == 1
    assert results[1].notifications_sent == 1


def test_fetch_billing_data_for_day_is_grouped_by_international(notify_db_session):
    service = create_service()
    template = create_template(service=service)
    create_notification(template=template, status='delivered', international=True)
    create_notification(template=template, status='delivered', international=False)

    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(today)
    assert len(results) == 2
    assert results[0].notifications_sent == 1
    assert results[1].notifications_sent == 1


def test_fetch_billing_data_for_day_is_grouped_by_notification_type(notify_db_session):
    service = create_service()
    sms_template = create_template(service=service, template_type='sms')
    email_template = create_template(service=service, template_type='email')
    letter_template = create_template(service=service, template_type='letter')
    create_notification(template=sms_template, status='delivered')
    create_notification(template=sms_template, status='delivered')
    create_notification(template=sms_template, status='delivered')
    create_notification(template=email_template, status='delivered')
    create_notification(template=email_template, status='delivered')
    create_notification(template=letter_template, status='delivered')

    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(today)
    assert len(results) == 3
    notification_types = [x[2] for x in results if x[2] in ['email', 'sms', 'letter']]
    assert len(notification_types) == 3


def test_fetch_billing_data_for_day_groups_by_postage(notify_db_session):
    service = create_service()
    letter_template = create_template(service=service, template_type='letter')
    email_template = create_template(service=service, template_type='email')
    create_notification(template=letter_template, status='delivered', postage='first')
    create_notification(template=letter_template, status='delivered', postage='first')
    create_notification(template=letter_template, status='delivered', postage='second')
    create_notification(template=email_template, status='delivered')

    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(today)
    assert len(results) == 3


def test_fetch_billing_data_for_day_sets_postage_for_emails_and_sms_to_none(notify_db_session):
    service = create_service()
    sms_template = create_template(service=service, template_type='sms')
    email_template = create_template(service=service, template_type='email')
    create_notification(template=sms_template, status='delivered')
    create_notification(template=email_template, status='delivered')

    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(today)
    assert len(results) == 2
    assert results[0].postage == 'none'
    assert results[1].postage == 'none'


def test_fetch_billing_data_for_day_returns_empty_list(notify_db_session):
    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(today)
    assert results == []


def test_fetch_billing_data_for_day_uses_notification_history(notify_db_session):
    service = create_service()
    sms_template = create_template(service=service, template_type='sms')
    create_notification(template=sms_template, status='delivered', created_at=datetime.utcnow() - timedelta(days=8))
    create_notification(template=sms_template, status='delivered', created_at=datetime.utcnow() - timedelta(days=8))

    Notification.query.delete()
    db.session.commit()
    results = fetch_billing_data_for_day(process_day=datetime.utcnow() - timedelta(days=8), service_id=service.id)
    assert len(results) == 1
    assert results[0].notifications_sent == 2


def test_fetch_billing_data_for_day_returns_list_for_given_service(notify_db_session):
    service = create_service()
    service_2 = create_service(service_name='Service 2')
    template = create_template(service=service)
    template_2 = create_template(service=service_2)
    create_notification(template=template, status='delivered')
    create_notification(template=template_2, status='delivered')

    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(process_day=today, service_id=service.id)
    assert len(results) == 1
    assert results[0].service_id == service.id


def test_fetch_billing_data_for_day_bills_correctly_for_status(notify_db_session):
    service = create_service()
    sms_template = create_template(service=service, template_type='sms')
    email_template = create_template(service=service, template_type='email')
    letter_template = create_template(service=service, template_type='letter')
    for status in NOTIFICATION_STATUS_TYPES:
        create_notification(template=sms_template, status=status)
        create_notification(template=email_template, status=status)
        create_notification(template=letter_template, status=status)
    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(process_day=today, service_id=service.id)

    sms_results = [x for x in results if x[2] == 'sms']
    email_results = [x for x in results if x[2] == 'email']
    letter_results = [x for x in results if x[2] == 'letter']
    assert 7 == sms_results[0][7]
    assert 7 == email_results[0][7]
    assert 3 == letter_results[0][7]


def test_get_rates_for_billing(notify_db_session):
    create_rate(start_date=datetime.utcnow(), value=12, notification_type='email')
    create_rate(start_date=datetime.utcnow(), value=22, notification_type='sms')
    create_rate(start_date=datetime.utcnow(), value=33, notification_type='email')
    non_letter_rates, letter_rates = get_rates_for_billing()

    assert len(non_letter_rates) == 3
    assert len(letter_rates) == 29


def test_get_rate(notify_db_session):
    create_rate(start_date=datetime.utcnow(), value=1.2, notification_type='email')
    create_rate(start_date=datetime.utcnow(), value=2.2, notification_type='sms')
    create_rate(start_date=datetime.utcnow(), value=3.3, notification_type='email')
    non_letter_rates, letter_rates = get_rates_for_billing()
    rate = get_rate(non_letter_rates=non_letter_rates, letter_rates=letter_rates, notification_type='sms',
                    date=datetime.utcnow())
    letter_rate = get_rate(non_letter_rates=non_letter_rates, letter_rates=letter_rates,
                           notification_type='letter',
                           crown=True,
                           letter_page_count=1,
                           date=datetime.utcnow())

    assert rate == 2.2
    assert letter_rate == Decimal('0.3')


@pytest.mark.parametrize("letter_post_class,expected_rate", [("first", "0.61"), ("second", "0.35")])
def test_get_rate_filters_letters_by_post_class(notify_db_session, letter_post_class, expected_rate):
    non_letter_rates, letter_rates = get_rates_for_billing()
    rate = get_rate(non_letter_rates, letter_rates, "letter", datetime(2018, 10, 1), True, 2, letter_post_class)
    assert rate == Decimal(expected_rate)


@pytest.mark.parametrize("date,expected_rate", [(datetime(2018, 9, 30), '0.33'), (datetime(2018, 10, 1), '0.35')])
def test_get_rate_chooses_right_rate_depending_on_date(notify_db_session, date, expected_rate):
    non_letter_rates, letter_rates = get_rates_for_billing()
    rate = get_rate(non_letter_rates, letter_rates, "letter", date, True, 2, "second")
    assert rate == Decimal(expected_rate)


def test_get_rate_for_letters_when_page_count_is_zero(notify_db_session):
    non_letter_rates, letter_rates = get_rates_for_billing()
    letter_rate = get_rate(non_letter_rates=non_letter_rates, letter_rates=letter_rates,
                           notification_type='letter',
                           crown=True,
                           letter_page_count=0,
                           date=datetime.utcnow())
    assert letter_rate == 0


def test_fetch_monthly_billing_for_year(notify_db_session):
    service = create_service()
    template = create_template(service=service, template_type="sms")
    for i in range(1, 31):
        create_ft_billing(bst_date='2018-06-{}'.format(i),
                          service=service,
                          template=template,
                          notification_type='sms',
                          rate_multiplier=2,
                          rate=0.162)
    for i in range(1, 32):
        create_ft_billing(bst_date='2018-07-{}'.format(i),
                          service=service,
                          template=template,
                          notification_type='sms',
                          rate=0.158)

    results = fetch_monthly_billing_for_year(service_id=service.id, year=2018)

    assert len(results) == 2
    assert str(results[0].month) == "2018-06-01"
    assert results[0].notifications_sent == 30
    assert results[0].billable_units == Decimal('60')
    assert results[0].rate == Decimal('0.162')
    assert results[0].notification_type == 'sms'
    assert results[0].postage == 'none'

    assert str(results[1].month) == "2018-07-01"
    assert results[1].notifications_sent == 31
    assert results[1].billable_units == Decimal('31')
    assert results[1].rate == Decimal('0.158')
    assert results[1].notification_type == 'sms'
    assert results[1].postage == 'none'


@freeze_time('2018-08-01 13:30:00')
def test_fetch_monthly_billing_for_year_adds_data_for_today(notify_db_session):
    service = create_service()
    template = create_template(service=service, template_type="email")
    for i in range(1, 32):
        create_ft_billing(bst_date='2018-07-{}'.format(i),
                          service=service,
                          template=template,
                          notification_type='email',
                          rate=0.162)
    create_notification(template=template, status='delivered')

    assert db.session.query(FactBilling.bst_date).count() == 31
    results = fetch_monthly_billing_for_year(service_id=service.id,
                                             year=2018)
    assert db.session.query(FactBilling.bst_date).count() == 32
    assert len(results) == 2


def test_fetch_monthly_billing_for_year_return_financial_year(notify_db_session):
    service = set_up_yearly_data()

    results = fetch_monthly_billing_for_year(service.id, 2016)
    # returns 3 rows, per month, returns financial year april to end of march
    # Orders by Month

    assert len(results) == 48
    assert str(results[0].month) == "2016-04-01"
    assert results[0].notification_type == 'email'
    assert results[0].notifications_sent == 30
    assert results[0].billable_units == 30
    assert results[0].rate == Decimal('0')
    assert str(results[1].month) == "2016-04-01"
    assert results[1].notification_type == 'letter'
    assert results[1].notifications_sent == 30
    assert results[1].billable_units == 30
    assert results[1].rate == Decimal('0.30')
    assert str(results[1].month) == "2016-04-01"
    assert results[2].notification_type == 'letter'
    assert results[2].notifications_sent == 30
    assert results[2].billable_units == 30
    assert results[2].rate == Decimal('0.33')
    assert str(results[3].month) == "2016-04-01"
    assert results[3].notification_type == 'sms'
    assert results[3].notifications_sent == 30
    assert results[3].billable_units == 30
    assert results[3].rate == Decimal('0.162')
    assert str(results[4].month) == "2016-05-01"
    assert str(results[47].month) == "2017-03-01"


def test_fetch_billing_totals_for_year(notify_db_session):
    service = set_up_yearly_data()
    results = fetch_billing_totals_for_year(service_id=service.id, year=2016)

    assert len(results) == 4
    assert results[0].notification_type == 'email'
    assert results[0].notifications_sent == 365
    assert results[0].billable_units == 365
    assert results[0].rate == Decimal('0')

    assert results[1].notification_type == 'letter'
    assert results[1].notifications_sent == 365
    assert results[1].billable_units == 365
    assert results[1].rate == Decimal('0.3')

    assert results[2].notification_type == 'letter'
    assert results[2].notifications_sent == 365
    assert results[2].billable_units == 365
    assert results[2].rate == Decimal('0.33')

    assert results[3].notification_type == 'sms'
    assert results[3].notifications_sent == 365
    assert results[3].billable_units == 365
    assert results[3].rate == Decimal('0.162')


def test_delete_billing_data(notify_db_session):
    service_1 = create_service(service_name='1')
    service_2 = create_service(service_name='2')
    sms_template = create_template(service_1, 'sms')
    email_template = create_template(service_1, 'email')
    other_service_template = create_template(service_2, 'sms')

    existing_rows_to_delete = [  # noqa
        create_ft_billing('2018-01-01', 'sms', sms_template, service_1, billable_unit=1),
        create_ft_billing('2018-01-01', 'email', email_template, service_1, billable_unit=2)
    ]
    other_day = create_ft_billing('2018-01-02', 'sms', sms_template, service_1, billable_unit=3)
    other_service = create_ft_billing('2018-01-01', 'sms', other_service_template, service_2, billable_unit=4)

    delete_billing_data_for_service_for_day('2018-01-01', service_1.id)

    current_rows = FactBilling.query.all()
    assert sorted(x.billable_units for x in current_rows) == sorted(
        [other_day.billable_units, other_service.billable_units]
    )
