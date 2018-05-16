from calendar import monthrange
from decimal import Decimal

from datetime import datetime, timedelta
from freezegun import freeze_time

from app import db
from app.dao.fact_billing_dao import (
    fetch_monthly_billing_for_year, fetch_billing_data_for_day, get_rates_for_billing,
    get_rate,
    fetch_billing_totals_for_year,
)
from app.models import FactBilling, Notification
from app.utils import convert_utc_to_bst
from tests.app.db import (
    create_ft_billing,
    create_service,
    create_template,
    create_notification,
    create_rate,
    create_letter_rate
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
                                  rate=0.33)
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


def test_get_rates_for_billing(notify_db_session):
    create_rate(start_date=datetime.utcnow(), value=12, notification_type='email')
    create_rate(start_date=datetime.utcnow(), value=22, notification_type='sms')
    create_rate(start_date=datetime.utcnow(), value=33, notification_type='email')
    create_letter_rate(start_date=datetime.utcnow())
    non_letter_rates, letter_rates = get_rates_for_billing()

    assert len(non_letter_rates) == 3
    assert len(letter_rates) == 1


def test_get_rate(notify_db_session):
    create_rate(start_date=datetime.utcnow(), value=1.2, notification_type='email')
    create_rate(start_date=datetime.utcnow(), value=2.2, notification_type='sms')
    create_rate(start_date=datetime.utcnow(), value=3.3, notification_type='email')
    create_letter_rate(start_date=datetime.utcnow(), rate=4.4)
    non_letter_rates, letter_rates = get_rates_for_billing()
    rate = get_rate(non_letter_rates=non_letter_rates, letter_rates=letter_rates, notification_type='sms',
                    date=datetime.utcnow())
    letter_rate = get_rate(non_letter_rates=non_letter_rates, letter_rates=letter_rates,
                           notification_type='letter',
                           crown=True,
                           rate_multiplier=1,
                           date=datetime.utcnow())

    assert rate == 2.2
    assert letter_rate == Decimal('4.4')


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

    assert str(results[1].month) == "2018-07-01"
    assert results[1].notifications_sent == 31
    assert results[1].billable_units == Decimal('31')
    assert results[1].rate == Decimal('0.158')
    assert results[1].notification_type == 'sms'


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

    assert len(results) == 36
    assert str(results[0].month) == "2016-04-01"
    assert results[0].notification_type == 'email'
    assert results[0].notifications_sent == 30
    assert results[0].billable_units == 30
    assert results[0].rate == Decimal('0')
    assert str(results[1].month) == "2016-04-01"
    assert results[1].notification_type == 'letter'
    assert results[1].notifications_sent == 30
    assert results[1].billable_units == 30
    assert results[1].rate == Decimal('0.33')
    assert str(results[2].month) == "2016-04-01"
    assert results[2].notification_type == 'sms'
    assert results[2].notifications_sent == 30
    assert results[2].billable_units == 30
    assert results[2].rate == Decimal('0.162')
    assert str(results[3].month) == "2016-05-01"
    assert str(results[35].month) == "2017-03-01"


def test_fetch_billing_totals_for_year(notify_db_session):
    service = set_up_yearly_data()
    results = fetch_billing_totals_for_year(service_id=service.id, year=2016)

    assert len(results) == 3
    assert results[0].notification_type == 'email'
    assert results[0].notifications_sent == 365
    assert results[0].billable_units == 365
    assert results[0].rate == Decimal('0')

    assert results[1].notification_type == 'letter'
    assert results[1].notifications_sent == 365
    assert results[1].billable_units == 365
    assert results[1].rate == Decimal('0.33')

    assert results[2].notification_type == 'sms'
    assert results[2].notifications_sent == 365
    assert results[2].billable_units == 365
    assert results[2].rate == Decimal('0.162')
