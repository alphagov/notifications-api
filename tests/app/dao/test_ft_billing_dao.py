from calendar import monthrange
from decimal import Decimal

from datetime import datetime, timedelta, date
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
    fetch_billing_for_all_services, fetch_sms_free_allowance_remainder
)
from app.dao.organisation_dao import dao_add_service_to_organisation
from app.models import (
    FactBilling,
    Notification,
    NOTIFICATION_STATUS_TYPES
)
from tests.app.db import (
    create_ft_billing,
    create_service,
    create_template,
    create_notification,
    create_rate,
    create_letter_rate,
    create_notification_history,
    create_organisation, create_annual_billing)


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


@freeze_time('2018-04-02 01:20:00')
def test_fetch_billing_data_for_today_includes_data_with_the_right_date(notify_db_session):
    process_day = datetime(2018, 4, 1, 13, 30, 0)
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
    create_notification_history(template=sms_template, status='delivered',
                                created_at=datetime.utcnow() - timedelta(days=8))
    create_notification_history(template=sms_template, status='delivered',
                                created_at=datetime.utcnow() - timedelta(days=8))

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
    create_letter_rate(start_date=datetime.utcnow(), rate=0.66, post_class='first')
    create_letter_rate(start_date=datetime.utcnow(), rate=0.33, post_class='second')
    non_letter_rates, letter_rates = get_rates_for_billing()

    assert len(non_letter_rates) == 3
    assert len(letter_rates) == 2


@freeze_time('2017-06-01 12:00')
def test_get_rate(notify_db_session):
    create_rate(start_date=datetime(2017, 5, 30, 23, 0), value=1.2, notification_type='email')
    create_rate(start_date=datetime(2017, 5, 30, 23, 0), value=2.2, notification_type='sms')
    create_rate(start_date=datetime(2017, 5, 30, 23, 0), value=3.3, notification_type='email')
    create_letter_rate(start_date=datetime(2017, 5, 30, 23, 0), rate=0.66, post_class='first')
    create_letter_rate(start_date=datetime(2017, 5, 30, 23, 0), rate=0.3, post_class='second')

    non_letter_rates, letter_rates = get_rates_for_billing()
    rate = get_rate(non_letter_rates=non_letter_rates, letter_rates=letter_rates, notification_type='sms',
                    date=date(2017, 6, 1))
    letter_rate = get_rate(non_letter_rates=non_letter_rates, letter_rates=letter_rates,
                           notification_type='letter',
                           crown=True,
                           letter_page_count=1,
                           date=date(2017, 6, 1))

    assert rate == 2.2
    assert letter_rate == Decimal('0.3')


@pytest.mark.parametrize("letter_post_class,expected_rate", [("first", "0.61"), ("second", "0.35")])
def test_get_rate_filters_letters_by_post_class(notify_db_session, letter_post_class, expected_rate):
    create_letter_rate(start_date=datetime(2017, 5, 30, 23, 0), sheet_count=2, rate=0.61, post_class='first')
    create_letter_rate(start_date=datetime(2017, 5, 30, 23, 0), sheet_count=2, rate=0.35, post_class='second')

    non_letter_rates, letter_rates = get_rates_for_billing()
    rate = get_rate(non_letter_rates, letter_rates, "letter", datetime(2018, 10, 1), True, 2, letter_post_class)
    assert rate == Decimal(expected_rate)


@pytest.mark.parametrize("date,expected_rate", [(datetime(2018, 9, 30), '0.33'), (datetime(2018, 10, 1), '0.35')])
def test_get_rate_chooses_right_rate_depending_on_date(notify_db_session, date, expected_rate):
    create_letter_rate(start_date=datetime(2016, 1, 1, 0, 0), sheet_count=2, rate=0.33, post_class='second')
    create_letter_rate(start_date=datetime(2018, 9, 30, 23, 0), sheet_count=2, rate=0.35, post_class='second')

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


def test_fetch_sms_free_allowance_remainder_with_remainder(notify_db_session):
    service = create_service(service_name='a test thing')
    create_annual_billing(service_id=service.id, free_sms_fragment_limit=3, financial_year_start=2016)
    create_ft_billing(service=service, bst_date=datetime(2016, 4,20), notification_type='sms', billable_unit=2)

    service_2 = create_service(service_name='b second thing')
    create_annual_billing(service_id=service_2.id, free_sms_fragment_limit=10, financial_year_start=2016)
    create_ft_billing(service=service_2, bst_date=datetime(2016, 4, 20), notification_type='sms', billable_unit=4)
    results = fetch_sms_free_allowance_remainder(datetime(2016, 10, 1)).all()

    assert len(results) == 2
    service_1_results = None
    service_2_results = None

    if results[0].service_id == service.id:
        service_1_results == results[0]
    else:
        service_2_results == results[0]

    if results[1].service_id == service.id:
        service_1_results == results[1]
    else:
        service_2_results == results[1]

    assert service_1_results.billable_units == 2
    assert service_1_results.free_sms_fragment_limit == 3

    assert service_1_results.sms_remainder == 1


# def test_fetch_sms_free_allowance_remainder_with_negative_remainder_returns_zero(notify_db_session):
#     service = create_service(service_name='test thing')
#     create_annual_billing(service_id=service.id, free_sms_fragment_limit=3, financial_year_start=2016)
#     create_ft_billing(service=service, bst_date=datetime(2016, 4,20), notification_type='sms', billable_unit=12)
#     results = fetch_sms_free_allowance_remainder(datetime(2016, 10, 1)).all()
#
#     assert results[0].service_id == service.id
#     assert results[0].billable_units == 12
#     assert results[0].free_sms_fragment_limit == 3
#     assert results[0].sms_remainder == 0


def test_fetch_billing_for_all_services_with_remainder(notify_db_session):
    service = create_service(service_name='has free allowance')
    org = create_organisation(name="Org for {}".format(service.name))
    dao_add_service_to_organisation(service=service, organisation_id=org.id)
    create_annual_billing(service_id=service.id, free_sms_fragment_limit=10, financial_year_start=2016)
    create_ft_billing(service=service, bst_date=datetime(2016, 4, 20), notification_type='sms', billable_unit=2,
                      rate=0.1)
    create_ft_billing(service=service, bst_date=datetime(2016, 5, 20), notification_type='sms', billable_unit=2,
                      rate=0.1)

    service_2 = create_service(service_name='used free allowance')
    org2 = create_organisation(name="Org for {}".format(service_2.name))
    dao_add_service_to_organisation(service=service_2, organisation_id=org.id)
    create_annual_billing(service_id=service_2.id, free_sms_fragment_limit=10, financial_year_start=2016)
    create_ft_billing(service=service_2, bst_date=datetime(2016, 4, 20), notification_type='sms', billable_unit=12,
                      rate=0.11)
    create_ft_billing(service=service_2, bst_date=datetime(2016, 5, 20), notification_type='sms', billable_unit=3,
                      rate=0.11)
    results = fetch_billing_for_all_services(datetime(2016, 5, 1), datetime(2016, 5, 31))
    print(results)
    assert len(results) == 2

    assert results[0].organisation_id == org.id
    assert results[0].service_id == service.id
    assert results[0].sms_billable_units == 2
    assert results[0].sms_remainder == 8
    assert results[0].remainder_minus_billable_units == 0
    assert results[0].sms_cost == 0

    # assert results[1].organisation_id == org2.id
    # assert results[1].service_id == service_2.id
    # assert results[1].sms_billable_units == 3
    # assert results[1].sms_remainder == 0
    # assert results[1].remainder_minus_billable_units == 3
    # assert results[1].sms_cost == 0.2

#
#
# def test_fetch_billing_for_all_services(notify_db_session):
#     set_up_quarterly_data()
#     set_up_quarterly_data(service_name='Second Service')
#
#     results = fetch_billing_for_all_services(datetime(2016, 4, 1), datetime(2016, 6, 30))
#     print(results)
#     assert len(results) == 2
#
#     assert results[0].organisation_name == 'Org for First service'
#     assert results[0].service_name == 'First service'
#     assert results[0].free_sms_fragment_limit == 25000
#     assert results[1].organisation_name == 'Org for Second Service'
#     assert results[1].service_name == 'Second Service'
#     assert results[1].free_sms_fragment_limit == 25000
#
#
# def set_up_quarterly_data(service_name='First service'):
#     year = 2016
#     org = create_organisation(name="Org for {}".format(service_name))
#     service = create_service(service_name=service_name)
#     dao_add_service_to_organisation(service=service, organisation_id=org.id)
#     create_annual_billing(service_id=service.id, free_sms_fragment_limit=25000, financial_year_start=year)
#     sms_template = create_template(service=service, template_type="sms")
#     email_template = create_template(service=service, template_type="email")
#     letter_template = create_template(service=service, template_type="letter")
#     for month in range(4, 6):
#         mon = str(month).zfill(2)
#         for day in range(1, 3):
#             d = str(day).zfill(2)
#             create_ft_billing(bst_date='{}-{}-{}'.format(year, mon, d),
#                               service=service,
#                               template=sms_template,
#                               notification_type='sms',
#                               rate=0.162)
#             create_ft_billing(bst_date='{}-{}-{}'.format(year, mon, d),
#                               service=service,
#                               template=email_template,
#                               notification_type='email',
#                               rate=0)
#             create_ft_billing(bst_date='{}-{}-{}'.format(year, mon, d),
#                               service=service,
#                               template=letter_template,
#                               notification_type='letter',
#                               rate=0.33,
#                               postage='second')
#             create_ft_billing(bst_date='{}-{}-{}'.format(year, mon, d),
#                               service=service,
#                               template=letter_template,
#                               notification_type='letter',
#                               rate=0.30,
#                               billable_unit=2,
#                               postage='first')
#     return service
