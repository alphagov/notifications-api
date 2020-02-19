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
    fetch_sms_free_allowance_remainder,
    fetch_sms_billing_for_all_services,
    fetch_letter_costs_for_all_services, fetch_letter_line_items_for_all_services)
from app.dao.organisation_dao import dao_add_service_to_organisation
from app.models import (
    FactBilling,
    NOTIFICATION_STATUS_TYPES,
)
from tests.app.db import (
    create_ft_billing,
    create_service,
    create_template,
    create_notification,
    create_rate,
    create_letter_rate,
    create_notification_history,
    create_annual_billing,
    create_organisation,
    create_service_data_retention,
    set_up_usage_data,
)


def set_up_yearly_data():
    service = create_service()
    sms_template = create_template(service=service, template_type="sms")
    email_template = create_template(service=service, template_type="email")
    letter_template = create_template(service=service, template_type="letter")

    start_date = date(2016, 3, 31)
    end_date = date(2017, 4, 2)

    for n in range((end_date - start_date).days):
        dt = start_date + timedelta(days=n)

        create_ft_billing(bst_date=dt, template=sms_template, rate=0.162)
        create_ft_billing(bst_date=dt, template=email_template, rate=0)
        create_ft_billing(bst_date=dt, template=letter_template, rate=0.33, postage='second')
        create_ft_billing(bst_date=dt, template=letter_template, rate=0.30, postage='second')
    return service


def test_fetch_billing_data_for_today_includes_data_with_the_right_key_type(notify_db_session):
    service = create_service()
    template = create_template(service=service, template_type="email")
    for key_type in ['normal', 'test', 'team']:
        create_notification(template=template, status='delivered', key_type=key_type)

    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(today.date())
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
    results = fetch_billing_data_for_day(day_under_test.date())
    assert len(results) == 1
    assert results[0].notifications_sent == 2


def test_fetch_billing_data_for_day_is_grouped_by_template_and_notification_type(notify_db_session):
    service = create_service()
    email_template = create_template(service=service, template_type="email")
    sms_template = create_template(service=service, template_type="sms")
    create_notification(template=email_template, status='delivered')
    create_notification(template=sms_template, status='delivered')

    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(today.date())
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
    results = fetch_billing_data_for_day(today.date())
    assert len(results) == 2
    assert results[0].notifications_sent == 1
    assert results[1].notifications_sent == 1


def test_fetch_billing_data_for_day_is_grouped_by_provider(notify_db_session):
    service = create_service()
    template = create_template(service=service)
    create_notification(template=template, status='delivered', sent_by='mmg')
    create_notification(template=template, status='delivered', sent_by='firetext')

    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(today.date())
    assert len(results) == 2
    assert results[0].notifications_sent == 1
    assert results[1].notifications_sent == 1


def test_fetch_billing_data_for_day_is_grouped_by_rate_mulitplier(notify_db_session):
    service = create_service()
    template = create_template(service=service)
    create_notification(template=template, status='delivered', rate_multiplier=1)
    create_notification(template=template, status='delivered', rate_multiplier=2)

    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(today.date())
    assert len(results) == 2
    assert results[0].notifications_sent == 1
    assert results[1].notifications_sent == 1


def test_fetch_billing_data_for_day_is_grouped_by_international(notify_db_session):
    service = create_service()
    template = create_template(service=service)
    create_notification(template=template, status='delivered', international=True)
    create_notification(template=template, status='delivered', international=False)

    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(today.date())
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
    results = fetch_billing_data_for_day(today.date())
    assert len(results) == 3
    notification_types = [x.notification_type for x in results]
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
    results = fetch_billing_data_for_day(today.date())
    assert len(results) == 3


def test_fetch_billing_data_for_day_groups_by_sent_by(notify_db_session):
    service = create_service()
    letter_template = create_template(service=service, template_type='letter')
    email_template = create_template(service=service, template_type='email')
    create_notification(template=letter_template, status='delivered', postage='second', sent_by='dvla')
    create_notification(template=letter_template, status='delivered', postage='second', sent_by='dvla')
    create_notification(template=letter_template, status='delivered', postage='second', sent_by=None)
    create_notification(template=email_template, status='delivered')

    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(today.date())
    assert len(results) == 2


def test_fetch_billing_data_for_day_groups_by_page_count(notify_db_session):
    service = create_service()
    letter_template = create_template(service=service, template_type='letter')
    email_template = create_template(service=service, template_type='email')
    create_notification(template=letter_template, status='delivered', postage='second', billable_units=1)
    create_notification(template=letter_template, status='delivered', postage='second', billable_units=1)
    create_notification(template=letter_template, status='delivered', postage='second', billable_units=2)
    create_notification(template=email_template, status='delivered')

    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(today.date())
    assert len(results) == 3


def test_fetch_billing_data_for_day_sets_postage_for_emails_and_sms_to_none(notify_db_session):
    service = create_service()
    sms_template = create_template(service=service, template_type='sms')
    email_template = create_template(service=service, template_type='email')
    create_notification(template=sms_template, status='delivered')
    create_notification(template=email_template, status='delivered')

    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(today.date())
    assert len(results) == 2
    assert results[0].postage == 'none'
    assert results[1].postage == 'none'


def test_fetch_billing_data_for_day_returns_empty_list(notify_db_session):
    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(today.date())
    assert results == []


def test_fetch_billing_data_for_day_uses_correct_table(notify_db_session):
    service = create_service()
    create_service_data_retention(service, notification_type='email', days_of_retention=3)
    sms_template = create_template(service=service, template_type='sms')
    email_template = create_template(service=service, template_type='email')

    five_days_ago = datetime.utcnow() - timedelta(days=5)
    create_notification(template=sms_template, status='delivered', created_at=five_days_ago)
    create_notification_history(template=email_template, status='delivered', created_at=five_days_ago)

    results = fetch_billing_data_for_day(process_day=five_days_ago.date(), service_id=service.id)
    assert len(results) == 2
    assert results[0].notification_type == 'sms'
    assert results[0].notifications_sent == 1
    assert results[1].notification_type == 'email'
    assert results[1].notifications_sent == 1


def test_fetch_billing_data_for_day_returns_list_for_given_service(notify_db_session):
    service = create_service()
    service_2 = create_service(service_name='Service 2')
    template = create_template(service=service)
    template_2 = create_template(service=service_2)
    create_notification(template=template, status='delivered')
    create_notification(template=template_2, status='delivered')

    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(process_day=today.date(), service_id=service.id)
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
    results = fetch_billing_data_for_day(process_day=today.date(), service_id=service.id)

    sms_results = [x for x in results if x.notification_type == 'sms']
    email_results = [x for x in results if x.notification_type == 'email']
    letter_results = [x for x in results if x.notification_type == 'letter']
    # we expect as many rows as we check for notification types
    assert 6 == sms_results[0].notifications_sent
    assert 4 == email_results[0].notifications_sent
    assert 3 == letter_results[0].notifications_sent

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
                          template=template,
                          rate_multiplier=2,
                          rate=0.162)
    for i in range(1, 32):
        create_ft_billing(bst_date='2018-07-{}'.format(i),
                          template=template,
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
        create_ft_billing(bst_date='2018-07-{}'.format(i), template=template)
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
        create_ft_billing('2018-01-01', sms_template, billable_unit=1),
        create_ft_billing('2018-01-01', email_template, billable_unit=2)
    ]
    other_day = create_ft_billing('2018-01-02', sms_template, billable_unit=3)
    other_service = create_ft_billing('2018-01-01', other_service_template, billable_unit=4)

    delete_billing_data_for_service_for_day('2018-01-01', service_1.id)

    current_rows = FactBilling.query.all()
    assert sorted(x.billable_units for x in current_rows) == sorted(
        [other_day.billable_units, other_service.billable_units]
    )


def test_fetch_sms_free_allowance_remainder_with_two_services(notify_db_session):
    service = create_service(service_name='has free allowance')
    template = create_template(service=service)
    org = create_organisation(name="Org for {}".format(service.name))
    dao_add_service_to_organisation(service=service, organisation_id=org.id)
    create_annual_billing(service_id=service.id, free_sms_fragment_limit=10, financial_year_start=2016)
    create_ft_billing(template=template, bst_date=datetime(2016, 4, 20), billable_unit=2, rate=0.11)
    create_ft_billing(template=template, bst_date=datetime(2016, 5, 20), billable_unit=3, rate=0.11)

    service_2 = create_service(service_name='used free allowance')
    template_2 = create_template(service=service_2)
    org_2 = create_organisation(name="Org for {}".format(service_2.name))
    dao_add_service_to_organisation(service=service_2, organisation_id=org_2.id)
    create_annual_billing(service_id=service_2.id, free_sms_fragment_limit=20, financial_year_start=2016)
    create_ft_billing(template=template_2, bst_date=datetime(2016, 4, 20), billable_unit=12, rate=0.11)
    create_ft_billing(template=template_2, bst_date=datetime(2016, 4, 22), billable_unit=10, rate=0.11)
    create_ft_billing(template=template_2, bst_date=datetime(2016, 5, 20), billable_unit=3, rate=0.11)

    results = fetch_sms_free_allowance_remainder(datetime(2016, 5, 1)).all()
    assert len(results) == 2
    service_result = [row for row in results if row[0] == service.id]
    assert service_result[0] == (service.id, 10, 2, 8)
    service_2_result = [row for row in results if row[0] == service_2.id]
    assert service_2_result[0] == (service_2.id, 20, 22, 0)


def test_fetch_sms_billing_for_all_services_for_first_quarter(notify_db_session):
    # This test is useful because the inner query resultset is empty.
    service = create_service(service_name='a - has free allowance')
    template = create_template(service=service)
    org = create_organisation(name="Org for {}".format(service.name))
    dao_add_service_to_organisation(service=service, organisation_id=org.id)
    create_annual_billing(service_id=service.id, free_sms_fragment_limit=25000, financial_year_start=2019)
    create_ft_billing(template=template, bst_date=datetime(2019, 4, 20), billable_unit=44, rate=0.11)
    results = fetch_sms_billing_for_all_services(datetime(2019, 4, 1), datetime(2019, 5, 30))
    assert len(results) == 1
    assert results[0] == (org.name, org.id, service.name, service.id, 25000, Decimal('0.11'), 25000, 44, 0,
                          Decimal('0'))


def test_fetch_sms_billing_for_all_services_with_remainder(notify_db_session):
    service = create_service(service_name='a - has free allowance')
    template = create_template(service=service)
    org = create_organisation(name="Org for {}".format(service.name))
    dao_add_service_to_organisation(service=service, organisation_id=org.id)
    create_annual_billing(service_id=service.id, free_sms_fragment_limit=10, financial_year_start=2019)
    create_ft_billing(template=template, bst_date=datetime(2019, 4, 20), billable_unit=2, rate=0.11)
    create_ft_billing(template=template, bst_date=datetime(2019, 5, 20), billable_unit=2, rate=0.11)
    create_ft_billing(template=template, bst_date=datetime(2019, 5, 22), billable_unit=1, rate=0.11)

    service_2 = create_service(service_name='b - used free allowance')
    template_2 = create_template(service=service_2)
    org_2 = create_organisation(name="Org for {}".format(service_2.name))
    dao_add_service_to_organisation(service=service_2, organisation_id=org_2.id)
    create_annual_billing(service_id=service_2.id, free_sms_fragment_limit=10, financial_year_start=2019)
    create_ft_billing(template=template_2, bst_date=datetime(2019, 4, 20), billable_unit=12, rate=0.11)
    create_ft_billing(template=template_2, bst_date=datetime(2019, 5, 20), billable_unit=3, rate=0.11)

    service_3 = create_service(service_name='c - partial allowance')
    template_3 = create_template(service=service_3)
    org_3 = create_organisation(name="Org for {}".format(service_3.name))
    dao_add_service_to_organisation(service=service_3, organisation_id=org_3.id)
    create_annual_billing(service_id=service_3.id, free_sms_fragment_limit=10, financial_year_start=2019)
    create_ft_billing(template=template_3, bst_date=datetime(2019, 4, 20), billable_unit=5, rate=0.11)
    create_ft_billing(template=template_3, bst_date=datetime(2019, 5, 20), billable_unit=7, rate=0.11)

    service_4 = create_service(service_name='d - email only')
    email_template = create_template(service=service_4, template_type='email')
    org_4 = create_organisation(name="Org for {}".format(service_4.name))
    dao_add_service_to_organisation(service=service_4, organisation_id=org_4.id)
    create_annual_billing(service_id=service_4.id, free_sms_fragment_limit=10, financial_year_start=2019)
    create_ft_billing(template=email_template, bst_date=datetime(2019, 5, 22), notifications_sent=5,
                      billable_unit=0, rate=0)

    results = fetch_sms_billing_for_all_services(datetime(2019, 5, 1), datetime(2019, 5, 31))
    assert len(results) == 3
    # (organisation_name, organisation_id, service_name, free_sms_fragment_limit, sms_rate,
    #  sms_remainder, sms_billable_units, chargeable_billable_sms, sms_cost)
    assert results[0] == (org.name, org.id, service.name, service.id, 10, Decimal('0.11'), 8, 3, 0, Decimal('0'))
    assert results[1] == (org_2.name, org_2.id, service_2.name, service_2.id, 10, Decimal('0.11'), 0, 3, 3,
                          Decimal('0.33'))
    assert results[2] == (org_3.name, org_3.id, service_3.name, service_3.id, 10, Decimal('0.11'), 5, 7, 2,
                          Decimal('0.22'))


def test_fetch_sms_billing_for_all_services_without_an_organisation_appears(notify_db_session):
    org, org_2, service, service_2, service_3, service_sms_only = set_up_usage_data(datetime(2019, 5, 1))
    results = fetch_sms_billing_for_all_services(datetime(2019, 5, 1), datetime(2019, 5, 31))

    assert len(results) == 2
    # organisation_name, organisation_id, service_name, service_id, free_sms_fragment_limit,
    # sms_rate, sms_remainder, sms_billable_units, chargeable_billable_units, sms_cost
    assert results[0] == (org.name, org.id, service.name, service.id, 10, Decimal('0.11'), 8, 3, 0, Decimal('0'))
    assert results[1] == (None, None, service_sms_only.name, service_sms_only.id, 10, Decimal('0.11'),
                          0, 3, 3, Decimal('0.33'))


def test_fetch_letter_costs_for_all_services(notify_db_session):
    org, org_2, service, service_2, service_3, service_sms_only = set_up_usage_data(datetime(2019, 6, 1))

    results = fetch_letter_costs_for_all_services(datetime(2019, 6, 1), datetime(2019, 9, 30))

    assert len(results) == 3
    assert results[0] == (org.name, org.id, service.name, service.id, Decimal('3.40'))
    assert results[1] == (org_2.name, org_2.id, service_2.name, service_2.id, Decimal('14.00'))
    assert results[2] == (None, None, service_3.name, service_3.id, Decimal('8.25'))


def test_fetch_letter_line_items_for_all_service(notify_db_session):
    org_1, org_2, service_1, service_2, service_3, service_sms_only = set_up_usage_data(datetime(2019, 6, 1))

    results = fetch_letter_line_items_for_all_services(datetime(2019, 6, 1), datetime(2019, 9, 30))

    assert len(results) == 5
    assert results[0] == (org_1.name, org_1.id, service_1.name, service_1.id, Decimal('0.45'), 'second', 6)
    assert results[1] == (org_1.name, org_1.id, service_1.name, service_1.id, Decimal("0.35"), 'first', 2)
    assert results[2] == (org_2.name, org_2.id, service_2.name, service_2.id, Decimal("0.65"), 'second', 20)
    assert results[3] == (org_2.name, org_2.id, service_2.name, service_2.id, Decimal("0.50"), 'first', 2)
    assert results[4] == (None, None, service_3.name, service_3.id, Decimal("0.55"), 'second', 15)
