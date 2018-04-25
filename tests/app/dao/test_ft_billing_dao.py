from decimal import Decimal

from datetime import datetime, timedelta
from freezegun import freeze_time

from app import db
from app.dao.fact_billing_dao import (
    fetch_annual_billing_for_year, fetch_billing_data_for_day, get_rates_for_billing,
    get_rate
)
from app.models import FactBilling
from app.utils import convert_utc_to_bst
from tests.app.db import (
    create_ft_billing,
    create_service,
    create_template,
    create_notification,
    create_rate,
    create_letter_rate
)


def test_fetch_billing_data_for_today_includes_data_with_the_right_status(notify_db_session):
    service = create_service()
    template = create_template(service=service, template_type="email")
    for status in ['delivered', 'sending', 'temporary-failure', 'created', 'technical-failure']:
        create_notification(template=template, status=status)

    today = convert_utc_to_bst(datetime.utcnow())
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


def test_fetch_billing_data_for_day_returns_empty_list(notify_db_session):
    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(today)
    assert results == []


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
    rate = get_rate(non_letter_rates=non_letter_rates, letter_rates=letter_rates, notification_type='sms', date=datetime.utcnow())
    letter_rate = get_rate(non_letter_rates=non_letter_rates, letter_rates=letter_rates,
                           notification_type='letter',
                           crown=True,
                           rate_multiplier=1,
                           date=datetime.utcnow())

    assert rate == 2.2
    assert letter_rate == Decimal('4.4')


def test_fetch_annual_billing_for_year(notify_db_session):
    service = create_service()
    template = create_template(service=service, template_type="sms")
    for i in range(1, 31):
        create_ft_billing(bst_date='2018-06-{}'.format(i),
                          service=service,
                          template=template,
                          notification_type='sms',
                          rate=0.162)
    for i in range(1, 32):
        create_ft_billing(bst_date='2018-07-{}'.format(i),
                          service=service,
                          template=template,
                          notification_type='sms',
                          rate=0.158)

    results = fetch_annual_billing_for_year(service_id=service.id,
                                            year=2018)

    assert len(results) == 2
    assert results[0][0] == 6.0
    assert results[0][1] == 30
    assert results[0][2] == Decimal('30')
    assert results[0][3] == service.id
    assert results[0][4] == Decimal('0.162')
    assert results[0][5] == Decimal('1')
    assert results[0][6] is False

    assert results[1][0] == 7.0
    assert results[1][1] == 31
    assert results[1][2] == Decimal('31')
    assert results[1][3] == service.id
    assert results[1][4] == Decimal('0.158')
    assert results[1][5] == Decimal('1')
    assert results[1][6] is False


@freeze_time('2018-08-01 13:30:00')
def test_fetch_annual_billing_for_year_adds_data_for_today(notify_db_session):
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
    results = fetch_annual_billing_for_year(service_id=service.id,
                                            year=2018)
    assert db.session.query(FactBilling.bst_date).count() == 32
    assert len(results) == 2
