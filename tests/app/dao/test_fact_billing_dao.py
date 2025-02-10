from collections import namedtuple
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from freezegun import freeze_time
from notifications_utils.timezones import convert_utc_to_bst

from app import db
from app.constants import NOTIFICATION_STATUS_TYPES
from app.dao.fact_billing_dao import (
    delete_billing_data_for_day,
    fetch_billing_data_for_day,
    fetch_daily_sms_provider_volumes_for_platform,
    fetch_daily_volumes_for_platform,
    fetch_usage_for_all_services_letter,
    fetch_usage_for_all_services_letter_breakdown,
    fetch_usage_for_all_services_sms,
    fetch_usage_for_organisation,
    fetch_usage_for_service_annual,
    fetch_usage_for_service_by_month,
    fetch_volumes_by_service,
    get_count_of_notifications_sent,
    get_organisation_live_services_and_their_free_allowance,
    get_rate,
    get_rates_for_billing,
    get_sms_fragments_sent_last_financial_year,
    update_ft_billing_letter_despatch,
)
from app.dao.notifications_dao import dao_record_letter_despatched_on_by_id
from app.dao.organisation_dao import dao_add_service_to_organisation
from app.models import FactBilling, FactBillingLetterDespatch, LetterCostThreshold, Service
from tests.app.db import (
    create_annual_billing,
    create_ft_billing,
    create_letter_rate,
    create_notification,
    create_notification_history,
    create_rate,
    create_service,
    create_service_data_retention,
    create_template,
    set_up_usage_data,
)


@pytest.fixture
def sample_service_billing_fy_2016(sample_service):
    sms_template = create_template(service=sample_service, template_type="sms")
    email_template = create_template(service=sample_service, template_type="email")
    letter_template = create_template(service=sample_service, template_type="letter")

    # use different rates for adjacent financial years to make sure the query
    # doesn't accidentally bleed over into them
    for dt in (date(2016, 3, 31), date(2017, 4, 1)):
        create_ft_billing(bst_date=dt, template=sms_template, rate=0.163)
        create_ft_billing(bst_date=dt, template=email_template, rate=0, billable_unit=0)
        create_ft_billing(bst_date=dt, template=letter_template, rate=0.31, postage="second")

    # also add annual billing for these adjacent years, which should not be used
    create_annual_billing(service_id=sample_service.id, free_sms_fragment_limit=9999, financial_year_start=2015)
    create_annual_billing(service_id=sample_service.id, free_sms_fragment_limit=8888, financial_year_start=2017)

    # a selection of dates that represent the extreme ends of the financial year
    # and some arbitrary dates in between
    for dt in (date(2016, 4, 1), date(2016, 4, 29), date(2017, 2, 6), date(2017, 3, 31)):
        create_ft_billing(bst_date=dt, template=sms_template, rate=0.162)
        create_ft_billing(bst_date=dt, template=email_template, rate=0, billable_unit=0)
        create_ft_billing(bst_date=dt, template=letter_template, rate=0.30, postage="second")

    create_annual_billing(service_id=sample_service.id, free_sms_fragment_limit=1, financial_year_start=2016)


@pytest.fixture
def sample_service_billing_fy_2018_variable_rates(sample_service):
    sms_template = create_template(service=sample_service, template_type="sms")
    letter_template = create_template(service=sample_service, template_type="letter")

    create_ft_billing(bst_date="2018-05-16", template=sms_template, rate=0.162)
    create_ft_billing(bst_date="2018-05-17", template=sms_template, rate_multiplier=2, rate=0.0150, billable_unit=2)
    create_ft_billing(bst_date="2018-05-16", template=sms_template, rate_multiplier=2, rate=0.162, billable_unit=2)
    create_ft_billing(bst_date="2018-05-16", template=letter_template, rate=0.33, postage="second")

    create_ft_billing(
        bst_date="2018-05-17",
        template=letter_template,
        rate=0.36,
        notifications_sent=2,
        billable_unit=4,  # 2 pages each
        postage="second",
    )

    # This amounts to a total SMS cost of 0.045:
    #
    #  - 5 free units on the 16th (rate=0.162)
    #  - 1 free unit on the 17th (rate=0.015)
    #  - 3 paid units on the 17th (rate=0.015)
    #
    create_annual_billing(service_id=sample_service.id, free_sms_fragment_limit=6, financial_year_start=2018)


def test_fetch_billing_data_for_today_includes_data_with_the_right_key_type(notify_db_session):
    service = create_service()
    template = create_template(service=service, template_type="email")
    for key_type in ["normal", "test", "team"]:
        create_notification(template=template, status="delivered", key_type=key_type)

    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(today.date())
    assert len(results) == 1
    assert results[0].notifications_sent == 2


@pytest.mark.parametrize("notification_type", ["email", "sms", "letter"])
def test_fetch_billing_data_for_day_only_calls_query_for_permission_type(notify_db_session, notification_type):
    service = create_service(service_permissions=[notification_type])
    email_template = create_template(service=service, template_type="email")
    sms_template = create_template(service=service, template_type="sms")
    letter_template = create_template(service=service, template_type="letter")
    create_notification(template=email_template, status="delivered")
    create_notification(template=sms_template, status="delivered")
    create_notification(template=letter_template, status="delivered")
    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(process_day=today.date(), check_permissions=True)
    assert len(results) == 1


@pytest.mark.parametrize("notification_type", ["email", "sms", "letter"])
def test_fetch_billing_data_for_day_only_calls_query_for_all_channels(notify_db_session, notification_type):
    service = create_service(service_permissions=[notification_type])
    email_template = create_template(service=service, template_type="email")
    sms_template = create_template(service=service, template_type="sms")
    letter_template = create_template(service=service, template_type="letter")
    create_notification(template=email_template, status="delivered")
    create_notification(template=sms_template, status="delivered")
    create_notification(template=letter_template, status="delivered")
    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(process_day=today.date(), check_permissions=False)
    assert len(results) == 3


@freeze_time("2018-04-02 01:20:00")
def test_fetch_billing_data_for_today_includes_data_with_the_right_date(notify_db_session):
    process_day = datetime(2018, 4, 1, 13, 30, 0)
    service = create_service()
    template = create_template(service=service, template_type="email")
    create_notification(template=template, status="delivered", created_at=process_day)
    create_notification(template=template, status="delivered", created_at=datetime(2018, 3, 31, 23, 23, 23))

    create_notification(template=template, status="delivered", created_at=datetime(2018, 3, 31, 20, 23, 23))
    create_notification(template=template, status="sending", created_at=process_day + timedelta(days=1))

    day_under_test = convert_utc_to_bst(process_day)
    results = fetch_billing_data_for_day(day_under_test.date())
    assert len(results) == 1
    assert results[0].notifications_sent == 2


def test_fetch_billing_data_for_day_is_grouped_by_template_and_notification_type(notify_db_session):
    service = create_service()
    email_template = create_template(service=service, template_type="email")
    sms_template = create_template(service=service, template_type="sms")
    create_notification(template=email_template, status="delivered")
    create_notification(template=sms_template, status="delivered")

    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(today.date())
    assert len(results) == 2
    assert results[0].notifications_sent == 1
    assert results[1].notifications_sent == 1


def test_fetch_billing_data_for_day_is_grouped_by_service(notify_db_session):
    service_1 = create_service()
    service_2 = create_service(service_name="Service 2")
    email_template = create_template(service=service_1)
    sms_template = create_template(service=service_2)
    create_notification(template=email_template, status="delivered")
    create_notification(template=sms_template, status="delivered")

    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(today.date())
    assert len(results) == 2
    assert results[0].notifications_sent == 1
    assert results[1].notifications_sent == 1


def test_fetch_billing_data_for_day_is_grouped_by_provider(notify_db_session):
    service = create_service()
    template = create_template(service=service)
    create_notification(template=template, status="delivered", sent_by="mmg")
    create_notification(template=template, status="delivered", sent_by="firetext")

    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(today.date())
    assert len(results) == 2
    assert results[0].notifications_sent == 1
    assert results[1].notifications_sent == 1


def test_fetch_billing_data_for_day_is_grouped_by_rate_mulitplier(notify_db_session):
    service = create_service()
    template = create_template(service=service)
    create_notification(template=template, status="delivered", rate_multiplier=1)
    create_notification(template=template, status="delivered", rate_multiplier=2)

    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(today.date())
    assert len(results) == 2
    assert results[0].notifications_sent == 1
    assert results[1].notifications_sent == 1


def test_fetch_billing_data_for_day_is_grouped_by_international(notify_db_session):
    service = create_service()
    sms_template = create_template(service=service)
    letter_template = create_template(template_type="letter", service=service)
    create_notification(template=sms_template, status="delivered", international=True)
    create_notification(template=sms_template, status="delivered", international=False)
    create_notification(template=letter_template, status="delivered", international=True)
    create_notification(template=letter_template, status="delivered", international=False)

    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(today.date())
    assert len(results) == 4
    assert all(result.notifications_sent == 1 for result in results)


def test_fetch_billing_data_for_day_is_grouped_by_notification_type(notify_db_session):
    service = create_service()
    sms_template = create_template(service=service, template_type="sms")
    email_template = create_template(service=service, template_type="email")
    letter_template = create_template(service=service, template_type="letter")
    create_notification(template=sms_template, status="delivered")
    create_notification(template=sms_template, status="delivered")
    create_notification(template=sms_template, status="delivered")
    create_notification(template=email_template, status="delivered")
    create_notification(template=email_template, status="delivered")
    create_notification(template=letter_template, status="delivered")

    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(today.date())
    assert len(results) == 3
    notification_types = [x.notification_type for x in results]
    assert len(notification_types) == 3


def test_fetch_billing_data_for_day_groups_by_postage(notify_db_session):
    service = create_service()
    letter_template = create_template(service=service, template_type="letter")
    email_template = create_template(service=service, template_type="email")
    create_notification(template=letter_template, status="delivered", postage="first")
    create_notification(template=letter_template, status="delivered", postage="first")
    create_notification(template=letter_template, status="delivered", postage="second")
    create_notification(template=letter_template, status="delivered", postage="europe")
    create_notification(template=letter_template, status="delivered", postage="rest-of-world")
    create_notification(template=email_template, status="delivered")

    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(today.date())
    assert len(results) == 5


def test_fetch_billing_data_for_day_groups_by_sent_by(notify_db_session):
    service = create_service()
    letter_template = create_template(service=service, template_type="letter")
    email_template = create_template(service=service, template_type="email")
    create_notification(template=letter_template, status="delivered", postage="second", sent_by="dvla")
    create_notification(template=letter_template, status="delivered", postage="second", sent_by="dvla")
    create_notification(template=letter_template, status="delivered", postage="second", sent_by=None)
    create_notification(template=email_template, status="delivered")

    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(today.date())
    assert len(results) == 2


def test_fetch_billing_data_for_day_groups_by_page_count(notify_db_session):
    service = create_service()
    letter_template = create_template(service=service, template_type="letter")
    email_template = create_template(service=service, template_type="email")
    create_notification(template=letter_template, status="delivered", postage="second", billable_units=1)
    create_notification(template=letter_template, status="delivered", postage="second", billable_units=1)
    create_notification(template=letter_template, status="delivered", postage="second", billable_units=2)
    create_notification(template=email_template, status="delivered")

    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(today.date())
    assert len(results) == 3


def test_fetch_billing_data_for_day_sets_postage_for_emails_and_sms_to_none(notify_db_session):
    service = create_service()
    sms_template = create_template(service=service, template_type="sms")
    email_template = create_template(service=service, template_type="email")
    create_notification(template=sms_template, status="delivered")
    create_notification(template=email_template, status="delivered")

    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(today.date())
    assert len(results) == 2
    assert results[0].postage == "none"
    assert results[1].postage == "none"


def test_fetch_billing_data_for_day_returns_empty_list(notify_db_session):
    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(today.date())
    assert results == []


def test_fetch_billing_data_for_day_uses_correct_table(notify_db_session):
    service = create_service()
    create_service_data_retention(service, notification_type="email", days_of_retention=3)
    sms_template = create_template(service=service, template_type="sms")
    email_template = create_template(service=service, template_type="email")

    five_days_ago = datetime.utcnow() - timedelta(days=5)
    create_notification(template=sms_template, status="delivered", created_at=five_days_ago)
    create_notification_history(template=email_template, status="delivered", created_at=five_days_ago)

    results = fetch_billing_data_for_day(process_day=five_days_ago.date(), service_ids=[service.id])
    assert len(results) == 2
    assert results[0].notification_type == "sms"
    assert results[0].notifications_sent == 1
    assert results[1].notification_type == "email"
    assert results[1].notifications_sent == 1


def test_fetch_billing_data_for_day_returns_list_for_given_service(notify_db_session):
    service = create_service()
    service_2 = create_service(service_name="Service 2")
    template = create_template(service=service)
    template_2 = create_template(service=service_2)
    create_notification(template=template, status="delivered")
    create_notification(template=template_2, status="delivered")

    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(process_day=today.date(), service_ids=[service.id])
    assert len(results) == 1
    assert results[0].service_id == service.id


def test_fetch_billing_data_for_day_bills_correctly_for_status(notify_db_session):
    service = create_service()
    sms_template = create_template(service=service, template_type="sms")
    email_template = create_template(service=service, template_type="email")
    letter_template = create_template(service=service, template_type="letter")
    for status in NOTIFICATION_STATUS_TYPES:
        create_notification(template=sms_template, status=status)
        create_notification(template=email_template, status=status)
        create_notification(template=letter_template, status=status)
    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(process_day=today.date(), service_ids=[service.id])

    sms_results = [x for x in results if x.notification_type == "sms"]
    email_results = [x for x in results if x.notification_type == "email"]
    letter_results = [x for x in results if x.notification_type == "letter"]
    # we expect as many rows as we check for notification types
    assert 6 == sms_results[0].notifications_sent
    assert 4 == email_results[0].notifications_sent
    assert 3 == letter_results[0].notifications_sent


def test_get_rates_for_billing(notify_db_session):
    create_rate(start_date=datetime.utcnow(), value=12, notification_type="email")
    create_rate(start_date=datetime.utcnow(), value=22, notification_type="sms")
    create_rate(start_date=datetime.utcnow(), value=33, notification_type="email")
    create_letter_rate(start_date=datetime.utcnow(), rate=0.66, post_class="first")
    create_letter_rate(start_date=datetime.utcnow(), rate=0.33, post_class="second")
    create_letter_rate(start_date=datetime.utcnow(), rate=0.84, post_class="europe")
    create_letter_rate(start_date=datetime.utcnow(), rate=0.84, post_class="rest-of-world")
    non_letter_rates, letter_rates = get_rates_for_billing()

    assert len(non_letter_rates) == 3
    assert len(letter_rates) == 4


@freeze_time("2017-06-01 12:00")
def test_get_rate(notify_db_session):
    create_rate(start_date=datetime(2017, 5, 30, 23, 0), value=1.2, notification_type="email")
    create_rate(start_date=datetime(2017, 5, 30, 23, 0), value=2.2, notification_type="sms")
    create_rate(start_date=datetime(2017, 5, 30, 23, 0), value=3.3, notification_type="email")
    create_letter_rate(start_date=datetime(2017, 5, 30, 23, 0), rate=0.66, post_class="first")
    create_letter_rate(start_date=datetime(2017, 5, 30, 23, 0), rate=0.3, post_class="second")

    non_letter_rates, letter_rates = get_rates_for_billing()
    rate = get_rate(
        non_letter_rates=non_letter_rates, letter_rates=letter_rates, notification_type="sms", date=date(2017, 6, 1)
    )
    letter_rate = get_rate(
        non_letter_rates=non_letter_rates,
        letter_rates=letter_rates,
        notification_type="letter",
        crown=True,
        letter_page_count=1,
        date=date(2017, 6, 1),
    )

    assert rate == 2.2
    assert letter_rate == Decimal("0.3")


@pytest.mark.parametrize(
    "letter_post_class,expected_rate",
    [
        ("first", "0.61"),
        ("second", "0.35"),
        ("europe", "0.92"),
        ("rest-of-world", "1.05"),
    ],
)
def test_get_rate_filters_letters_by_post_class(notify_db_session, letter_post_class, expected_rate):
    create_letter_rate(start_date=datetime(2017, 5, 30, 23, 0), sheet_count=2, rate=0.61, post_class="first")
    create_letter_rate(start_date=datetime(2017, 5, 30, 23, 0), sheet_count=2, rate=0.35, post_class="second")
    create_letter_rate(start_date=datetime(2017, 5, 30, 23, 0), sheet_count=2, rate=0.92, post_class="europe")
    create_letter_rate(start_date=datetime(2017, 5, 30, 23, 0), sheet_count=2, rate=1.05, post_class="rest-of-world")

    non_letter_rates, letter_rates = get_rates_for_billing()
    rate = get_rate(non_letter_rates, letter_rates, "letter", datetime(2018, 10, 1), True, 2, letter_post_class)
    assert rate == Decimal(expected_rate)


@pytest.mark.parametrize("date,expected_rate", [(datetime(2018, 9, 30), "0.33"), (datetime(2018, 10, 1), "0.35")])
def test_get_rate_chooses_right_rate_depending_on_date(notify_db_session, date, expected_rate):
    create_letter_rate(start_date=datetime(2016, 1, 1, 0, 0), sheet_count=2, rate=0.33, post_class="second")
    create_letter_rate(start_date=datetime(2018, 9, 30, 23, 0), sheet_count=2, rate=0.35, post_class="second")

    non_letter_rates, letter_rates = get_rates_for_billing()
    rate = get_rate(non_letter_rates, letter_rates, "letter", date, True, 2, "second")
    assert rate == Decimal(expected_rate)


def test_get_rate_for_letters_when_page_count_is_zero(notify_db_session):
    non_letter_rates, letter_rates = get_rates_for_billing()
    letter_rate = get_rate(
        non_letter_rates=non_letter_rates,
        letter_rates=letter_rates,
        notification_type="letter",
        crown=True,
        letter_page_count=0,
        date=datetime.utcnow(),
    )
    assert letter_rate == 0


def test_fetch_usage_for_service_by_month(
    sample_service,
    sample_service_billing_fy_2016,
    notify_db_session,
):
    results = fetch_usage_for_service_by_month(sample_service.id, 2016)
    assert len(results) == 9  # 3 billed months for each type

    assert str(results[0].month) == "2016-04-01"
    assert results[0].notification_type == "email"
    assert results[0].notifications_sent == 2
    assert results[0].chargeable_units == 0
    assert results[0].rate == Decimal("0")
    assert results[0].cost == Decimal("0")
    assert results[0].free_allowance_used == 0
    assert results[0].charged_units == 0

    assert str(results[1].month) == "2016-04-01"
    assert results[1].notification_type == "letter"
    assert results[1].notifications_sent == 2
    assert results[1].chargeable_units == 2
    assert results[1].rate == Decimal("0.30")
    assert results[1].cost == Decimal("0.60")
    assert results[1].free_allowance_used == 0
    assert results[1].charged_units == 2

    assert str(results[2].month) == "2016-04-01"
    assert results[2].notification_type == "sms"
    assert results[2].notifications_sent == 2
    assert results[2].chargeable_units == 2
    assert results[2].rate == Decimal("0.162")
    # free allowance is 1
    assert results[2].cost == Decimal("0.162")
    assert results[2].free_allowance_used == 1
    assert results[2].charged_units == 1

    assert str(results[3].month) == "2017-02-01"
    assert str(results[8].month) == "2017-03-01"


def test_fetch_usage_for_service_by_month_variable_rates(
    sample_service,
    sample_service_billing_fy_2018_variable_rates,
    notify_db_session,
):
    results = fetch_usage_for_service_by_month(sample_service.id, 2018)
    assert len(results) == 4

    # Test data is only for the month of May
    assert str(results[0].month) == "2018-05-01"
    assert results[0].notification_type == "letter"
    assert results[0].notifications_sent == 1
    assert results[0].chargeable_units == 1
    assert results[0].rate == Decimal("0.33")
    assert results[0].cost == Decimal("0.33")
    assert results[0].free_allowance_used == 0
    assert results[0].charged_units == 1

    assert str(results[1].month) == "2018-05-01"
    assert results[1].notification_type == "letter"
    assert results[1].notifications_sent == 2
    assert results[1].chargeable_units == 2
    assert results[1].rate == Decimal("0.36")
    assert results[1].cost == Decimal("0.72")
    assert results[1].free_allowance_used == 0
    assert results[1].charged_units == 2

    assert str(results[2].month) == "2018-05-01"
    assert results[2].notification_type == "sms"
    assert results[2].notifications_sent == 1
    assert results[2].chargeable_units == 4
    assert results[2].rate == Decimal("0.015")
    assert results[2].cost == Decimal("0.045")
    assert results[2].free_allowance_used == 1
    assert results[2].charged_units == 3

    assert str(results[3].month) == "2018-05-01"
    assert results[3].notification_type == "sms"
    assert results[3].notifications_sent == 2
    assert results[3].chargeable_units == 5
    assert results[3].rate == Decimal("0.162")
    assert results[3].cost == Decimal("0")
    assert results[3].free_allowance_used == 5
    assert results[3].charged_units == 0


@freeze_time("2018-08-01 13:30:00")
def test_fetch_usage_for_service_by_month_populates_ft_billing_for_today(notify_db_session):
    service = create_service()
    template = create_template(service=service, template_type="sms")

    create_rate(start_date=datetime.utcnow() - timedelta(days=1), value=0.158, notification_type="sms")
    create_annual_billing(service_id=service.id, free_sms_fragment_limit=1000, financial_year_start=2018)

    for i in range(1, 32):
        create_ft_billing(bst_date=f"2018-07-{i}", template=template)

    create_notification(template=template, status="delivered")

    assert db.session.query(FactBilling.bst_date).count() == 31
    results = fetch_usage_for_service_by_month(service_id=service.id, year=2018)

    assert db.session.query(FactBilling.bst_date).count() == 32
    assert len(results) == 2


def test_fetch_usage_for_service_annual(
    sample_service,
    sample_service_billing_fy_2016,
    notify_db_session,
):
    results = fetch_usage_for_service_annual(service_id=sample_service.id, year=2016)
    assert len(results) == 3

    assert results[0].notification_type == "email"
    assert results[0].notifications_sent == 4
    assert results[0].chargeable_units == 0
    assert results[0].rate == Decimal("0")
    assert results[0].cost == Decimal("0")
    assert results[0].free_allowance_used == 0
    assert results[0].charged_units == 0

    assert results[1].notification_type == "letter"
    assert results[1].notifications_sent == 4
    assert results[1].chargeable_units == 4
    assert results[1].rate == Decimal("0.3")
    assert results[1].cost == Decimal("1.2")
    assert results[1].free_allowance_used == 0
    assert results[1].charged_units == 4

    assert results[2].notification_type == "sms"
    assert results[2].notifications_sent == 4
    assert results[2].chargeable_units == 4
    assert results[2].rate == Decimal("0.162")
    assert results[2].cost == Decimal("0.486")
    assert results[2].free_allowance_used == 1
    assert results[2].charged_units == 3


def test_fetch_usage_for_service_annual_variable_rates(
    sample_service,
    sample_service_billing_fy_2018_variable_rates,
    notify_db_session,
):
    results = fetch_usage_for_service_annual(service_id=sample_service.id, year=2018)
    assert len(results) == 4

    assert results[0].notification_type == "letter"
    assert results[0].notifications_sent == 1
    assert results[0].chargeable_units == 1
    assert results[0].rate == Decimal("0.33")
    assert results[0].cost == Decimal("0.33")
    assert results[0].free_allowance_used == 0
    assert results[0].charged_units == 1

    assert results[1].notification_type == "letter"
    assert results[1].notifications_sent == 2
    assert results[1].chargeable_units == 2
    assert results[1].rate == Decimal("0.36")
    assert results[1].cost == Decimal("0.72")
    assert results[1].free_allowance_used == 0
    assert results[1].charged_units == 2

    assert results[2].notification_type == "sms"
    assert results[2].notifications_sent == 1
    assert results[2].chargeable_units == 4
    assert results[2].rate == Decimal("0.015")
    assert results[2].cost == Decimal("0.045")
    assert results[2].free_allowance_used == 1
    assert results[2].charged_units == 3

    assert results[3].notification_type == "sms"
    assert results[3].notifications_sent == 2
    assert results[3].chargeable_units == 5
    assert results[3].rate == Decimal("0.162")
    assert results[3].cost == Decimal("0")
    assert results[3].free_allowance_used == 5
    assert results[3].charged_units == 0


def test_delete_billing_data(notify_db_session):
    service_1 = create_service(service_name="1")
    service_2 = create_service(service_name="2")
    sms_template = create_template(service_1, "sms")
    email_template = create_template(service_1, "email")
    other_service_template = create_template(service_2, "sms")

    # ft_billing rows for service_1 to delete
    create_ft_billing("2018-01-01", sms_template, billable_unit=1)
    create_ft_billing("2018-01-01", email_template, billable_unit=2)

    other_day = create_ft_billing("2018-01-02", sms_template, billable_unit=3)
    other_service = create_ft_billing("2018-01-01", other_service_template, billable_unit=4)

    deleted_rows = delete_billing_data_for_day("2018-01-01", [service_1.id])

    assert deleted_rows == 2

    current_rows = FactBilling.query.all()
    assert sorted(x.billable_units for x in current_rows) == sorted(
        [other_day.billable_units, other_service.billable_units]
    )


def test_delete_billing_data_when_no_service_ids_are_provided(notify_db_session):
    service_1 = create_service(service_name="1")
    service_2 = create_service(service_name="2")
    sms_template = create_template(service_1, "sms")
    email_template = create_template(service_1, "email")
    other_service_template = create_template(service_2, "sms")

    # ft_billing rows for service_1 and service_2 for provided day
    create_ft_billing("2018-01-01", sms_template, billable_unit=1)
    create_ft_billing("2018-01-01", email_template, billable_unit=2)
    create_ft_billing("2018-01-01", other_service_template, billable_unit=4)

    other_day = create_ft_billing("2018-01-02", sms_template, billable_unit=3)

    deleted_rows = delete_billing_data_for_day("2018-01-01")

    assert deleted_rows == 3

    current_rows = FactBilling.query.all()
    assert len(current_rows) == 1
    assert current_rows[0].billable_units == other_day.billable_units


def test_fetch_usage_for_all_services_sms(
    sample_service,
    sample_organisation,
    sample_service_billing_fy_2016,
    notify_db_session,
):
    dao_add_service_to_organisation(service=sample_service, organisation_id=sample_organisation.id)
    results = fetch_usage_for_all_services_sms(datetime(2016, 4, 1), datetime(2017, 3, 31)).all()

    assert len(results) == 1
    row_1 = results[0]

    assert row_1["organisation_name"] == sample_organisation.name
    assert row_1["organisation_id"] == sample_organisation.id
    assert row_1["service_name"] == sample_service.name
    assert row_1["service_id"] == sample_service.id
    assert row_1["free_allowance"] == 1
    assert row_1["free_allowance_left"] == 0
    assert row_1["chargeable_units"] == 4
    assert row_1["charged_units"] == 3
    assert row_1["cost"] == Decimal("0.486")


def test_fetch_usage_for_all_services_sms_with_organisation_id_filter(
    sample_service,
    sample_organisation,
    sample_service_billing_fy_2016,
    notify_db_session,
):
    dao_add_service_to_organisation(service=sample_service, organisation_id=sample_organisation.id)
    results = fetch_usage_for_all_services_sms(
        datetime(2016, 4, 1), datetime(2017, 3, 31), organisation_id=sample_organisation.id
    ).all()

    assert len(results) == 1
    row_1 = results[0]

    assert row_1["organisation_name"] == sample_organisation.name
    assert row_1["organisation_id"] == sample_organisation.id
    assert row_1["service_name"] == sample_service.name
    assert row_1["service_id"] == sample_service.id
    assert row_1["free_allowance"] == 1
    assert row_1["free_allowance_left"] == 0
    assert row_1["chargeable_units"] == 4
    assert row_1["charged_units"] == 3
    assert row_1["cost"] == Decimal("0.486")


def test_fetch_usage_for_all_services_sms_with_organisation_id_filter_for_a_different_organisation(
    sample_service,
    sample_organisation,
    sample_service_billing_fy_2016,
    notify_db_session,
):
    dao_add_service_to_organisation(service=sample_service, organisation_id=sample_organisation.id)
    results = fetch_usage_for_all_services_sms(
        datetime(2016, 4, 1), datetime(2017, 3, 31), organisation_id="aaaabbbb-cccc-dddd-eeee-ffffaaaabbbb"
    ).all()

    assert len(results) == 0


def test_fetch_usage_for_all_services_variable_rates(
    sample_service, sample_organisation, sample_service_billing_fy_2018_variable_rates, notify_db_session
):
    results = fetch_usage_for_all_services_sms(datetime(2018, 4, 1), datetime(2019, 3, 31)).all()
    assert len(results) == 1

    row = results[0]
    assert row["free_allowance"] == 6
    assert row["free_allowance_left"] == 0
    assert row["chargeable_units"] == 9
    assert row["charged_units"] == 3
    assert row["cost"] == Decimal("0.045")


def test_fetch_usage_for_all_services_sms_remainder(sample_service, sample_sms_template, notify_db_session):
    create_ft_billing(template=sample_sms_template, bst_date=datetime(2016, 4, 22), billable_unit=1)
    create_annual_billing(service_id=sample_service.id, free_sms_fragment_limit=3, financial_year_start=2016)
    results = fetch_usage_for_all_services_sms(datetime(2016, 4, 1), datetime(2017, 3, 31)).all()

    assert len(results) == 1
    row_1 = results[0]
    assert row_1["free_allowance_left"] == 2


def test_fetch_usage_for_all_services_sms_no_usage(sample_service, notify_db_session):
    create_annual_billing(service_id=sample_service.id, free_sms_fragment_limit=3, financial_year_start=2016)
    results = fetch_usage_for_all_services_sms(datetime(2016, 4, 1), datetime(2017, 3, 31)).all()
    assert len(results) == 0


def test_fetch_usage_for_all_services_sms_no_usage_in_period(
    sample_service,
    sample_sms_template,
    notify_db_session,
):
    create_ft_billing(template=sample_sms_template, bst_date=datetime(2016, 4, 22), billable_unit=5)
    create_annual_billing(service_id=sample_service.id, free_sms_fragment_limit=25000, financial_year_start=2016)

    results = fetch_usage_for_all_services_sms(datetime(2016, 11, 1), datetime(2017, 1, 31)).all()
    assert len(results) == 0


def test_fetch_usage_for_all_services_sms_includes_trial_services(
    sample_service, sample_sms_template, notify_db_session
):
    create_ft_billing(template=sample_sms_template, bst_date=datetime(2016, 4, 22), billable_unit=5)
    create_annual_billing(service_id=sample_service.id, free_sms_fragment_limit=1000, financial_year_start=2016)

    sample_service.restricted = True
    results = fetch_usage_for_all_services_sms(datetime(2016, 4, 1), datetime(2017, 3, 31)).all()
    assert len(results) > 0


def test_fetch_usage_for_all_services_sms_excludes_email(sample_service, notify_db_session):
    create_annual_billing(service_id=sample_service.id, free_sms_fragment_limit=25000, financial_year_start=2016)
    template = create_template(service=sample_service, template_type="email")
    create_ft_billing(template=template, bst_date=datetime(2016, 4, 22), notifications_sent=5, billable_unit=0)

    results = fetch_usage_for_all_services_sms(datetime(2016, 4, 1), datetime(2017, 3, 31)).all()
    assert len(results) == 0


def test_fetch_usage_for_all_services_sms_partially_billable(sample_service, sample_sms_template, notify_db_session):
    create_annual_billing(service_id=sample_service.id, free_sms_fragment_limit=3, financial_year_start=2019)
    create_ft_billing(template=sample_sms_template, bst_date=datetime(2019, 4, 20), billable_unit=5, rate=0.11)

    results = fetch_usage_for_all_services_sms(datetime(2019, 4, 1), datetime(2019, 5, 31)).all()
    assert len(results) == 1

    row = results[0]
    assert row["free_allowance_left"] == 0
    assert row["chargeable_units"] == 5
    assert row["charged_units"] == 2
    assert row["cost"] == Decimal("0.22")


def test_fetch_usage_for_all_services_sms_multiple_services(notify_db_session):
    service_1 = create_service(service_name="Service 1")
    service_1_template = create_template(service=service_1, template_type="sms")
    create_ft_billing(template=service_1_template, bst_date=datetime(2016, 4, 20), billable_unit=4, rate=0.162)
    create_annual_billing(service_id=service_1.id, free_sms_fragment_limit=3, financial_year_start=2016)

    service_2 = create_service(service_name="Service 2")
    service_2_template = create_template(service=service_2, template_type="sms")
    create_ft_billing(template=service_2_template, bst_date=datetime(2016, 4, 20), billable_unit=4, rate=0.162)
    create_annual_billing(service_id=service_2.id, free_sms_fragment_limit=6, financial_year_start=2016)

    results = fetch_usage_for_all_services_sms(datetime(2016, 4, 1), datetime(2017, 3, 31)).all()
    results = sorted(results, key=lambda row: row["service_name"])
    assert len(results) == 2

    service_1_row = results[0]
    assert service_1_row["free_allowance_left"] == 0
    assert service_1_row["chargeable_units"] == 4
    assert service_1_row["charged_units"] == 1
    assert service_1_row["cost"] == Decimal("0.162")

    service_2_row = results[1]
    assert service_2_row["free_allowance_left"] == 2
    assert service_2_row["chargeable_units"] == 4
    assert service_2_row["charged_units"] == 0
    assert service_2_row["cost"] == 0


def test_fetch_usage_for_all_services_sms_no_org(sample_service, sample_sms_template, notify_db_session):
    create_annual_billing(service_id=sample_service.id, free_sms_fragment_limit=1000, financial_year_start=2016)
    create_ft_billing(template=sample_sms_template, bst_date=datetime(2016, 4, 20), billable_unit=5)

    results = fetch_usage_for_all_services_sms(datetime(2016, 4, 15), datetime(2016, 5, 31)).all()
    assert len(results) == 1

    row_1 = results[0]
    assert row_1["organisation_name"] is None
    assert row_1["organisation_id"] is None
    assert row_1["service_name"] == sample_service.name
    assert row_1["service_id"] == sample_service.id


def test_fetch_usage_for_all_services_without_annual_billing(
    sample_service,
    notify_db_session,
):
    # Example: we don't continue populating annual_billing for inactive services
    sample_service.active = False
    results = fetch_usage_for_all_services_sms(datetime(2016, 4, 15), datetime(2016, 5, 31)).all()
    assert len(results) == 0


def test_fetch_usage_for_all_services_letter(notify_db_session):
    fixtures = set_up_usage_data(datetime(2019, 6, 1))

    results = fetch_usage_for_all_services_letter(datetime(2019, 6, 1), datetime(2019, 9, 30)).all()

    assert len(results) == 3
    assert results[0] == (
        fixtures["org_1"].name,
        fixtures["org_1"].id,
        fixtures["service_1_sms_and_letter"].name,
        fixtures["service_1_sms_and_letter"].id,
        8,
        Decimal("3.40"),
    )
    assert results[1] == (
        fixtures["org_for_service_with_letters"].name,
        fixtures["org_for_service_with_letters"].id,
        fixtures["service_with_letters"].name,
        fixtures["service_with_letters"].id,
        22,
        Decimal("14.00"),
    )
    assert results[2] == (
        None,
        None,
        fixtures["service_with_letters_without_org"].name,
        fixtures["service_with_letters_without_org"].id,
        18,
        Decimal("24.45"),
    )


def test_fetch_usage_for_all_services_letter_breakdown(notify_db_session):
    fixtures = set_up_usage_data(datetime(2019, 6, 1))

    results = fetch_usage_for_all_services_letter_breakdown(datetime(2019, 6, 1), datetime(2019, 9, 30)).all()

    assert len(results) == 7
    assert results[0] == (
        fixtures["org_1"].name,
        fixtures["org_1"].id,
        fixtures["service_1_sms_and_letter"].name,
        fixtures["service_1_sms_and_letter"].id,
        Decimal("0.45"),
        "second",
        6,
    )
    assert results[1] == (
        fixtures["org_1"].name,
        fixtures["org_1"].id,
        fixtures["service_1_sms_and_letter"].name,
        fixtures["service_1_sms_and_letter"].id,
        Decimal("0.35"),
        "first",
        2,
    )
    assert results[2] == (
        fixtures["org_for_service_with_letters"].name,
        fixtures["org_for_service_with_letters"].id,
        fixtures["service_with_letters"].name,
        fixtures["service_with_letters"].id,
        Decimal("0.65"),
        "second",
        20,
    )
    assert results[3] == (
        fixtures["org_for_service_with_letters"].name,
        fixtures["org_for_service_with_letters"].id,
        fixtures["service_with_letters"].name,
        fixtures["service_with_letters"].id,
        Decimal("0.50"),
        "first",
        2,
    )
    assert results[4] == (
        None,
        None,
        fixtures["service_with_letters_without_org"].name,
        fixtures["service_with_letters_without_org"].id,
        Decimal("0.35"),
        "second",
        2,
    )
    assert results[5] == (
        None,
        None,
        fixtures["service_with_letters_without_org"].name,
        fixtures["service_with_letters_without_org"].id,
        Decimal("0.50"),
        "first",
        1,
    )
    assert results[6] == (
        None,
        None,
        fixtures["service_with_letters_without_org"].name,
        fixtures["service_with_letters_without_org"].id,
        Decimal("1.55"),
        "international",
        15,
    )


def test_fetch_usage_for_organisation(
    sample_service, sample_organisation, sample_service_billing_fy_2016, notify_db_session
):
    dao_add_service_to_organisation(service=sample_service, organisation_id=sample_organisation.id)
    results, updated_at = fetch_usage_for_organisation(sample_organisation.id, 2016)
    assert len(results) == 1
    assert updated_at is None

    first_row = results[str(sample_service.id)]
    assert first_row["service_id"] == sample_service.id
    assert first_row["service_name"] == sample_service.name
    assert first_row["free_sms_limit"] == 1
    assert first_row["sms_remainder"] == 0
    assert first_row["chargeable_billable_sms"] == 3
    assert first_row["sms_cost"] == 0.486
    assert first_row["letter_cost"] == 1.2  # 30p each
    assert first_row["emails_sent"] == 4


def test_fetch_usage_for_organisation_includes_updated_at_from_cache_for_current_year(
    sample_service, sample_organisation, sample_service_billing_fy_2016, notify_db_session, mocker
):
    dao_add_service_to_organisation(service=sample_service, organisation_id=sample_organisation.id)
    mocker.patch(
        "app.dao.fact_billing_dao.get_ft_billing_data_for_today_updated_at", return_value="2016-06-01T12:00:00+00:00"
    )

    with freeze_time("2016-06-01"):
        results, updated_at = fetch_usage_for_organisation(sample_organisation.id, 2016)
    assert len(results) == 1
    assert updated_at == "2016-06-01T12:00:00+00:00"

    first_row = results[str(sample_service.id)]
    assert first_row["service_id"] == sample_service.id
    assert first_row["service_name"] == sample_service.name
    assert first_row["free_sms_limit"] == 1
    assert first_row["sms_remainder"] == 0
    assert first_row["chargeable_billable_sms"] == 3
    assert first_row["sms_cost"] == 0.486
    assert first_row["letter_cost"] == 1.2  # 30p each
    assert first_row["emails_sent"] == 4


def test_fetch_usage_for_organisation_variable_rates(
    sample_service,
    sample_organisation,
    sample_service_billing_fy_2018_variable_rates,
    notify_db_session,
):
    dao_add_service_to_organisation(service=sample_service, organisation_id=sample_organisation.id)
    results, _ = fetch_usage_for_organisation(organisation_id=sample_organisation.id, year=2018)

    assert len(results) == 1
    row = results[str(sample_service.id)]

    assert row["free_sms_limit"] == 6
    assert row["sms_remainder"] == 0
    assert row["sms_billable_units"] == 9
    assert row["chargeable_billable_sms"] == 3
    assert row["sms_cost"] == 0.045


def test_fetch_usage_for_organisation_sms_remainder(
    sample_service, sample_organisation, sample_sms_template, notify_db_session
):
    dao_add_service_to_organisation(service=sample_service, organisation_id=sample_organisation.id)
    create_annual_billing(service_id=sample_service.id, free_sms_fragment_limit=3, financial_year_start=2016)
    create_ft_billing(template=sample_sms_template, bst_date=datetime(2016, 4, 20), billable_unit=1)

    results, _ = fetch_usage_for_organisation(organisation_id=sample_organisation.id, year=2016)
    assert len(results) == 1

    row = results[str(sample_service.id)]
    assert row["sms_remainder"] == 2


def test_fetch_usage_for_organisation_no_usage(
    sample_service,
    sample_organisation,
    notify_db_session,
):
    dao_add_service_to_organisation(service=sample_service, organisation_id=sample_organisation.id)
    create_annual_billing(service_id=sample_service.id, free_sms_fragment_limit=3, financial_year_start=2016)

    results, _ = fetch_usage_for_organisation(organisation_id=sample_organisation.id, year=2016)
    assert len(results) == 1

    row = results[str(sample_service.id)]
    assert row["free_sms_limit"] == 3
    assert row["sms_remainder"] == 3
    assert row["sms_billable_units"] == 0
    assert row["chargeable_billable_sms"] == 0
    assert row["sms_cost"] == 0.0


def test_fetch_usage_for_organisation_excludes_trial_services(
    sample_service,
    sample_organisation,
    sample_sms_template,
    notify_db_session,
):
    dao_add_service_to_organisation(service=sample_service, organisation_id=sample_organisation.id)
    create_annual_billing(service_id=sample_service.id, free_sms_fragment_limit=3, financial_year_start=2016)

    results, _ = fetch_usage_for_organisation(organisation_id=sample_organisation.id, year=2016)
    assert len(results) == 1

    sample_service.restricted = True
    results, _ = fetch_usage_for_organisation(organisation_id=sample_organisation.id, year=2016)
    assert len(results) == 0


def test_fetch_usage_for_organisation_partially_billable(
    sample_service,
    sample_organisation,
    sample_sms_template,
    notify_db_session,
):
    dao_add_service_to_organisation(service=sample_service, organisation_id=sample_organisation.id)
    create_annual_billing(service_id=sample_service.id, free_sms_fragment_limit=3, financial_year_start=2019)
    create_ft_billing(template=sample_sms_template, bst_date=datetime(2019, 4, 20), billable_unit=5, rate=0.11)

    results, _ = fetch_usage_for_organisation(sample_organisation.id, 2019)
    assert len(results) == 1

    row = results[str(sample_service.id)]
    assert row["sms_remainder"] == 0
    assert row["sms_billable_units"] == 5
    assert row["chargeable_billable_sms"] == 2
    assert row["sms_cost"] == 0.22


def test_fetch_usage_for_organisation_multiple_services(
    sample_organisation,
    notify_db_session,
):
    service_1 = create_service(service_name="Service 1")
    dao_add_service_to_organisation(service=service_1, organisation_id=sample_organisation.id)
    service_1_template = create_template(service=service_1, template_type="sms")
    create_ft_billing(template=service_1_template, bst_date=datetime(2016, 4, 20), billable_unit=4, rate=0.162)
    create_annual_billing(service_id=service_1.id, free_sms_fragment_limit=3, financial_year_start=2016)

    service_2 = create_service(service_name="Service 2")
    dao_add_service_to_organisation(service=service_2, organisation_id=sample_organisation.id)
    service_2_template = create_template(service=service_2, template_type="sms")
    create_ft_billing(template=service_2_template, bst_date=datetime(2016, 4, 20), billable_unit=4, rate=0.162)
    create_annual_billing(service_id=service_2.id, free_sms_fragment_limit=6, financial_year_start=2016)

    results, _ = fetch_usage_for_organisation(sample_organisation.id, 2016)
    assert len(results) == 2

    service_1_row = results[str(service_1.id)]
    assert service_1_row["sms_billable_units"] == 4
    assert service_1_row["chargeable_billable_sms"] == 1
    assert service_1_row["sms_cost"] == 0.162

    service_2_row = results[str(service_2.id)]
    assert service_2_row["sms_billable_units"] == 4
    assert service_2_row["chargeable_billable_sms"] == 0
    assert service_2_row["sms_cost"] == 0


def test_fetch_usage_for_organisation_without_annual_billing(
    sample_service, sample_organisation, sample_sms_template, notify_db_session
):
    # Example: we don't continue populating annual_billing for inactive services
    sample_service.active = False
    dao_add_service_to_organisation(service=sample_service, organisation_id=sample_organisation.id)

    results, _ = fetch_usage_for_organisation(sample_organisation.id, 2016)
    assert len(results) == 1

    row = results[str(sample_service.id)]
    assert row["sms_remainder"] == 0
    assert row["sms_billable_units"] == 0
    assert row["chargeable_billable_sms"] == 0
    assert row["sms_cost"] == 0


def test_fetch_daily_volumes_for_platform(
    notify_db_session, sample_template, sample_email_template, sample_letter_template
):
    create_ft_billing(bst_date="2022-02-03", template=sample_template, notifications_sent=10, billable_unit=10)
    create_ft_billing(
        bst_date="2022-02-03", template=sample_template, notifications_sent=10, billable_unit=30, international=True
    )
    create_ft_billing(bst_date="2022-02-03", template=sample_email_template, notifications_sent=10)
    create_ft_billing(
        bst_date="2022-02-03", template=sample_letter_template, notifications_sent=5, billable_unit=5, rate=0.39
    )
    create_ft_billing(
        bst_date="2022-02-03", template=sample_letter_template, notifications_sent=5, billable_unit=10, rate=0.44
    )

    create_ft_billing(bst_date="2022-02-04", template=sample_template, notifications_sent=20, billable_unit=40)
    create_ft_billing(
        bst_date="2022-02-04", template=sample_template, notifications_sent=10, billable_unit=20, rate_multiplier=3
    )
    create_ft_billing(bst_date="2022-02-04", template=sample_email_template, notifications_sent=50)
    create_ft_billing(bst_date="2022-02-04", template=sample_letter_template, notifications_sent=20, billable_unit=40)

    results = fetch_daily_volumes_for_platform(start_date="2022-02-03", end_date="2022-02-04")

    assert len(results) == 2
    assert results[0].bst_date == "2022-02-03"
    assert results[0].sms_totals == 20
    assert results[0].sms_fragment_totals == 40
    assert results[0].sms_chargeable_units == 40
    assert results[0].email_totals == 10
    assert results[0].letter_totals == 10
    assert results[0].letter_sheet_totals == 15

    assert results[1].bst_date == "2022-02-04"
    assert results[1].sms_totals == 30
    assert results[1].sms_fragment_totals == 60
    assert results[1].sms_chargeable_units == 100
    assert results[1].email_totals == 50
    assert results[1].letter_totals == 20
    assert results[1].letter_sheet_totals == 40


def test_fetch_daily_sms_provider_volumes_for_platform_groups_values_by_provider(
    notify_db_session,
):
    services = [create_service(service_name="a"), create_service(service_name="b")]
    templates = [create_template(services[0]), create_template(services[1])]

    create_ft_billing("2022-02-01", templates[0], provider="foo", notifications_sent=1, billable_unit=2)
    create_ft_billing("2022-02-01", templates[1], provider="foo", notifications_sent=4, billable_unit=8)

    create_ft_billing("2022-02-01", templates[0], provider="bar", notifications_sent=16, billable_unit=32)
    create_ft_billing("2022-02-01", templates[1], provider="bar", notifications_sent=64, billable_unit=128)

    results = fetch_daily_sms_provider_volumes_for_platform(start_date="2022-02-01", end_date="2022-02-01")

    assert len(results) == 2
    assert results[0].provider == "bar"
    assert results[0].sms_totals == 80
    assert results[0].sms_fragment_totals == 160

    assert results[1].provider == "foo"
    assert results[1].sms_totals == 5
    assert results[1].sms_fragment_totals == 10


def test_fetch_daily_sms_provider_volumes_for_platform_for_platform_calculates_chargeable_units_and_costs(
    sample_template,
):
    create_ft_billing("2022-02-01", sample_template, rate_multiplier=3, rate=1.5, notifications_sent=1, billable_unit=2)

    results = fetch_daily_sms_provider_volumes_for_platform(start_date="2022-02-01", end_date="2022-02-01")

    assert len(results) == 1
    assert results[0].sms_totals == 1
    assert results[0].sms_fragment_totals == 2
    assert results[0].sms_chargeable_units == 6
    assert results[0].sms_cost == 9


def test_fetch_daily_sms_provider_volumes_for_platform_for_platform_searches_dates_inclusively(sample_template):
    # too early
    create_ft_billing("2022-02-02", sample_template)

    # just right
    create_ft_billing("2022-02-03", sample_template)
    create_ft_billing("2022-02-04", sample_template)
    create_ft_billing("2022-02-05", sample_template)

    # too late
    create_ft_billing("2022-02-06", sample_template)

    results = fetch_daily_sms_provider_volumes_for_platform(start_date="2022-02-03", end_date="2022-02-05")

    assert len(results) == 3
    assert results[0].bst_date == date(2022, 2, 3)
    assert results[-1].bst_date == date(2022, 2, 5)


def test_fetch_daily_sms_provider_volumes_for_platform_for_platform_only_returns_sms(
    sample_template, sample_email_template, sample_letter_template
):
    create_ft_billing("2022-02-01", sample_template, notifications_sent=1)
    create_ft_billing("2022-02-01", sample_email_template, notifications_sent=2)
    create_ft_billing("2022-02-01", sample_letter_template, notifications_sent=4)

    results = fetch_daily_sms_provider_volumes_for_platform(start_date="2022-02-01", end_date="2022-02-01")

    assert len(results) == 1
    assert results[0].sms_totals == 1


def test_fetch_volumes_by_service(notify_db_session):
    set_up_usage_data(datetime(2022, 2, 1))

    results = fetch_volumes_by_service(start_date=datetime(2022, 2, 1), end_date=datetime(2022, 2, 28))

    # since we are using a pre-set up fixture, we only care about some of the results
    assert len(results) == 7
    assert results[0].service_name == "a - with sms and letter"
    assert results[0].organisation_name == "Org for a - with sms and letter"
    assert results[0].free_allowance == 10
    assert results[0].sms_notifications == 2
    assert results[0].sms_chargeable_units == 3
    assert results[0].email_totals == 0
    assert results[0].letter_totals == 4
    assert results[0].letter_sheet_totals == 6
    assert float(results[0].letter_cost) == 1.6

    assert results[1].service_name == "f - without ft_billing"
    assert results[1].organisation_name == "Org for a - with sms and letter"
    assert results[1].free_allowance == 10
    assert results[1].sms_notifications == 0
    assert results[1].sms_chargeable_units == 0
    assert results[1].email_totals == 0
    assert results[1].letter_totals == 0
    assert results[1].letter_sheet_totals == 0
    assert float(results[1].letter_cost) == 0

    assert results[4].service_name == "b - chargeable sms"
    assert not results[4].organisation_name
    assert results[4].free_allowance == 10
    assert results[4].sms_notifications == 2
    assert results[4].sms_chargeable_units == 3
    assert results[4].email_totals == 0
    assert results[4].letter_totals == 0
    assert results[4].letter_sheet_totals == 0
    assert float(results[4].letter_cost) == 0

    assert results[6].service_name == "e - sms within allowance"
    assert not results[6].organisation_name
    assert results[6].free_allowance == 10
    assert results[6].sms_notifications == 1
    assert results[6].sms_chargeable_units == 2
    assert results[6].email_totals == 0
    assert results[6].letter_totals == 0
    assert results[6].letter_sheet_totals == 0
    assert float(results[6].letter_cost) == 0


def test_fetch_volumes_by_service_returns_free_allowance_for_end_date(sample_service):
    create_annual_billing(service_id=sample_service.id, free_sms_fragment_limit=1000, financial_year_start=2023)
    create_annual_billing(service_id=sample_service.id, free_sms_fragment_limit=50, financial_year_start=2022)
    create_annual_billing(service_id=sample_service.id, free_sms_fragment_limit=7, financial_year_start=2021)

    results = fetch_volumes_by_service(start_date=datetime(2021, 4, 1), end_date=datetime(2022, 2, 28))

    assert len(results) == 1
    assert results[0].free_allowance == 50


class TestUpdateFtBillingLetterDespatch:
    def test_inserts_all_expected_records(self, sample_service):
        despatch_date = date(2020, 1, 1)
        create_letter_rate(start_date=datetime(2020, 1, 1, 0, 0), rate=1, sheet_count=1, post_class="first")
        create_letter_rate(start_date=datetime(2020, 1, 1, 0, 0), rate=0.5, sheet_count=2, post_class="second")
        create_letter_rate(start_date=datetime(2020, 1, 1, 0, 0), rate=0.75, sheet_count=3, post_class="second")
        create_letter_rate(start_date=datetime(2020, 1, 1, 0, 0), rate=1.5, sheet_count=4, post_class="europe")

        # Send 1x 1st class (1 page), 1x 2nd class (1 page), 2x 2nd class (2 pages), 1x europe (3 pages)
        letter_template = create_template(service=sample_service, template_type="letter")
        noti_1 = create_notification(template=letter_template, postage="first", billable_units=1, status="delivered")
        noti_2 = create_notification(template=letter_template, postage="first", billable_units=1, status="delivered")
        noti_3 = create_notification(template=letter_template, postage="second", billable_units=2, status="delivered")
        noti_4 = create_notification(template=letter_template, postage="second", billable_units=3, status="delivered")
        noti_5 = create_notification(template=letter_template, postage="second", billable_units=3, status="delivered")
        noti_6 = create_notification(template=letter_template, postage="second", billable_units=3, status="delivered")
        noti_7 = create_notification(template=letter_template, postage="europe", billable_units=4, status="delivered")
        dao_record_letter_despatched_on_by_id(
            notification_id=noti_1.id, despatched_on=despatch_date, cost_threshold=LetterCostThreshold.sorted
        )
        dao_record_letter_despatched_on_by_id(
            notification_id=noti_2.id, despatched_on=despatch_date, cost_threshold=LetterCostThreshold.unsorted
        )
        dao_record_letter_despatched_on_by_id(
            notification_id=noti_3.id, despatched_on=despatch_date, cost_threshold=LetterCostThreshold.sorted
        )
        dao_record_letter_despatched_on_by_id(
            notification_id=noti_4.id, despatched_on=despatch_date, cost_threshold=LetterCostThreshold.sorted
        )
        dao_record_letter_despatched_on_by_id(
            notification_id=noti_5.id, despatched_on=despatch_date, cost_threshold=LetterCostThreshold.sorted
        )
        dao_record_letter_despatched_on_by_id(
            notification_id=noti_6.id, despatched_on=despatch_date, cost_threshold=LetterCostThreshold.unsorted
        )
        dao_record_letter_despatched_on_by_id(
            notification_id=noti_7.id, despatched_on=despatch_date, cost_threshold=LetterCostThreshold.sorted
        )

        assert FactBillingLetterDespatch.query.count() == 0

        num_records, deleted = update_ft_billing_letter_despatch(despatch_date)

        assert num_records == 6
        assert deleted == 0

        facts = FactBillingLetterDespatch.query.order_by(FactBillingLetterDespatch.billable_units).all()
        assert len(facts) == 6
        assert facts[0].billable_units == 1
        assert facts[0].rate == 1
        assert facts[0].cost_threshold == LetterCostThreshold.sorted
        assert facts[0].postage == "first"

        assert facts[1].billable_units == 1
        assert facts[1].rate == 1
        assert facts[1].cost_threshold == LetterCostThreshold.unsorted
        assert facts[1].postage == "first"

        assert facts[2].billable_units == 2
        assert facts[2].rate == 0.5
        assert facts[2].cost_threshold == LetterCostThreshold.sorted
        assert facts[2].postage == "second"

        assert facts[3].billable_units == 3
        assert facts[3].rate == 0.75
        assert facts[3].cost_threshold == LetterCostThreshold.sorted
        assert facts[3].postage == "second"

        assert facts[4].billable_units == 3
        assert facts[4].rate == 0.75
        assert facts[4].cost_threshold == LetterCostThreshold.unsorted
        assert facts[4].postage == "second"

        assert facts[5].billable_units == 4
        assert facts[5].rate == 1.5
        assert facts[5].cost_threshold == LetterCostThreshold.sorted
        assert facts[5].postage == "europe"

    def test_deletes_records_that_no_longer_exist(self, notify_db_session):
        despatch_date = date(2020, 1, 1)
        fact = FactBillingLetterDespatch(
            bst_date=despatch_date,
            billable_units=1,
            rate=1,
            postage="first",
            cost_threshold=LetterCostThreshold.sorted,
            notifications_sent=1,
        )
        db.session.add(fact)
        db.session.commit()

        num_records, deleted = update_ft_billing_letter_despatch(despatch_date)

        assert num_records == 0
        assert deleted == 1
        assert FactBillingLetterDespatch.query.count() == 0

    def test_can_upsert(self, notify_db_session, sample_service):
        despatch_date = date(2020, 1, 1)
        letter_template = create_template(service=sample_service, template_type="letter")
        create_letter_rate(start_date=datetime(2020, 1, 1, 0, 0), rate=1, sheet_count=1, post_class="first")
        notification = create_notification(
            template=letter_template, postage="first", billable_units=1, status="delivered", reference="first1s"
        )
        dao_record_letter_despatched_on_by_id(
            notification_id=notification.id, despatched_on=despatch_date, cost_threshold=LetterCostThreshold.sorted
        )

        # We have an outdated billing fact that says 3 notifications were sent but there's actually only 1, so
        # when we re-run update_ft_billing_letter_despatch the 3 should become a 1.
        fact = FactBillingLetterDespatch(
            bst_date=despatch_date,
            billable_units=1,
            rate=1,
            postage="first",
            cost_threshold=LetterCostThreshold.sorted,
            notifications_sent=3,
        )
        db.session.add(fact)
        db.session.commit()

        assert fact.updated_at is None

        with freeze_time("2023-01-01T12:00:00"):
            num_records, deleted = update_ft_billing_letter_despatch(despatch_date)

        assert num_records == 1
        assert deleted == 0

        facts = FactBillingLetterDespatch.query.all()
        assert len(facts) == 1
        assert facts[0].billable_units == 1
        assert facts[0].rate == 1
        assert facts[0].postage == "first"
        assert facts[0].notifications_sent == 1
        assert facts[0].updated_at == datetime(2023, 1, 1, 12, 0, 0)


NotificationCountTestCase = namedtuple(
    "NotificationCountTestCase", ["notifications_data", "template_types", "limit_days", "expected_count"]
)

test_cases = [
    NotificationCountTestCase(
        notifications_data=[
            {"bst_date": "2023-08-09", "template_type": "sms", "notifications_sent": 2},
            {"bst_date": "2023-08-08", "template_type": "sms", "notifications_sent": 3},
            {"bst_date": "2023-08-07", "template_type": "email", "notifications_sent": 4},
            {"bst_date": "2023-07-25", "template_type": "sms", "notifications_sent": 20},  # Before limit_days
        ],
        template_types=["sms", "email"],
        limit_days=7,
        expected_count=9,  # 2+3+4
    ),
    NotificationCountTestCase(
        notifications_data=[
            {"bst_date": "2023-08-09", "template_type": "sms", "notifications_sent": 2},
            {"bst_date": "2023-08-08", "template_type": "sms", "notifications_sent": 3},
            {"bst_date": "2023-08-07", "template_type": "email", "notifications_sent": 4},
            {"bst_date": "2023-07-25", "template_type": "sms", "notifications_sent": 20},  # Before limit_days
        ],
        template_types=["sms"],
        limit_days=7,
        expected_count=5,  # 2+3
    ),
    NotificationCountTestCase(
        notifications_data=[
            {"bst_date": "2023-08-01", "template_type": "sms", "notifications_sent": 10},
            {"bst_date": "2023-08-02", "template_type": "sms", "notifications_sent": 15},
            {"bst_date": "2023-08-03", "template_type": "email", "notifications_sent": 5},
            {"bst_date": "2023-07-25", "template_type": "sms", "notifications_sent": 20},  # Before limit_days
        ],
        template_types=["sms", "email"],
        limit_days=2,
        expected_count=0,  # No notifications within the last 2 days
    ),
]


@freeze_time("2023-08-10")
@pytest.mark.parametrize(
    "test_case",
    test_cases,
    ids=["All template types within 7 days", "Only SMS template type within 7 days", "Limit days exclude all data"],
)
def test_get_count_of_notifications_sent(sample_service, test_case):
    assert len(FactBilling.query.all()) == 0

    sms_template = create_template(service=sample_service, template_type="sms")
    email_template = create_template(service=sample_service, template_type="email")

    for notification_data in test_case.notifications_data:
        template = sms_template if notification_data["template_type"] == "sms" else email_template
        create_ft_billing(
            bst_date=notification_data["bst_date"],
            template=template,
            notifications_sent=notification_data["notifications_sent"],
        )

    count = get_count_of_notifications_sent(
        service_id=sample_service.id, template_types=test_case.template_types, limit_days=test_case.limit_days
    )

    assert count == test_case.expected_count


@freeze_time("2019-04-02 01:20:00")
def test_get_sms_fragments_sent_last_financial_year(sample_service, sample_service_billing_fy_2018_variable_rates):
    sms_template = create_template(sample_service, "sms")
    # These rows should not get counted since they are before the last fy
    create_ft_billing("2018-01-01", sms_template)
    create_ft_billing("2017-08-01", sms_template)

    assert get_sms_fragments_sent_last_financial_year(sample_service.id) == 9


def test_get_organisation_live_services_with_free_allowance(sample_service, sample_organisation):
    service_with_no_free_allowance = create_service(service_name="service 2")

    create_annual_billing(sample_service.id, free_sms_fragment_limit=10, financial_year_start=2015)
    create_annual_billing(sample_service.id, free_sms_fragment_limit=20, financial_year_start=2016)

    dao_add_service_to_organisation(sample_service, sample_organisation.id)
    dao_add_service_to_organisation(service_with_no_free_allowance, sample_organisation.id)

    org_services = (
        get_organisation_live_services_and_their_free_allowance(sample_organisation.id, 2015)
        .order_by(Service.name)
        .all()
    )

    assert len(org_services) == 2

    assert org_services[0].id == sample_service.id
    assert org_services[0].free_sms_fragment_limit == 10

    assert org_services[1].id == service_with_no_free_allowance.id
    assert org_services[1].free_sms_fragment_limit == 0
