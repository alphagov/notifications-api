import uuid
from _decimal import Decimal
from datetime import datetime, timedelta

from freezegun import freeze_time

from app.dao.date_util import get_financial_year
from app.dao.notification_usage_dao import (
    get_rates_for_daterange,
    get_billing_data_for_month,
    get_monthly_billing_data,
    billing_letter_data_per_month_query
)
from app.models import (
    Rate,
    SMS_TYPE,
)
from tests.app.db import create_notification, create_rate, create_letter_rate, create_template, create_service


def test_get_rates_for_daterange(notify_db, notify_db_session):
    set_up_rate(notify_db, datetime(2016, 5, 18), 0.016)
    set_up_rate(notify_db, datetime(2017, 3, 31, 23), 0.0158)
    start_date, end_date = get_financial_year(2017)
    rates = get_rates_for_daterange(start_date, end_date, SMS_TYPE)
    assert len(rates) == 1
    assert datetime.strftime(rates[0].valid_from, '%Y-%m-%d %H:%M:%S') == "2017-03-31 23:00:00"
    assert rates[0].rate == 0.0158


def test_get_rates_for_daterange_multiple_result_per_year(notify_db, notify_db_session):
    set_up_rate(notify_db, datetime(2016, 4, 1), 0.015)
    set_up_rate(notify_db, datetime(2016, 5, 18), 0.016)
    set_up_rate(notify_db, datetime(2017, 4, 1), 0.0158)
    start_date, end_date = get_financial_year(2016)
    rates = get_rates_for_daterange(start_date, end_date, SMS_TYPE)
    assert len(rates) == 2
    assert datetime.strftime(rates[0].valid_from, '%Y-%m-%d %H:%M:%S') == "2016-04-01 00:00:00"
    assert rates[0].rate == 0.015
    assert datetime.strftime(rates[1].valid_from, '%Y-%m-%d %H:%M:%S') == "2016-05-18 00:00:00"
    assert rates[1].rate == 0.016


def test_get_rates_for_daterange_returns_correct_rates(notify_db, notify_db_session):
    set_up_rate(notify_db, datetime(2016, 4, 1), 0.015)
    set_up_rate(notify_db, datetime(2016, 9, 1), 0.016)
    set_up_rate(notify_db, datetime(2017, 6, 1), 0.0175)
    start_date, end_date = get_financial_year(2017)
    rates_2017 = get_rates_for_daterange(start_date, end_date, SMS_TYPE)
    assert len(rates_2017) == 2
    assert datetime.strftime(rates_2017[0].valid_from, '%Y-%m-%d %H:%M:%S') == "2016-09-01 00:00:00"
    assert rates_2017[0].rate == 0.016
    assert datetime.strftime(rates_2017[1].valid_from, '%Y-%m-%d %H:%M:%S') == "2017-06-01 00:00:00"
    assert rates_2017[1].rate == 0.0175


def test_get_rates_for_daterange_in_the_future(notify_db, notify_db_session):
    set_up_rate(notify_db, datetime(2016, 4, 1), 0.015)
    set_up_rate(notify_db, datetime(2017, 6, 1), 0.0175)
    start_date, end_date = get_financial_year(2018)
    rates = get_rates_for_daterange(start_date, end_date, SMS_TYPE)
    assert datetime.strftime(rates[0].valid_from, '%Y-%m-%d %H:%M:%S') == "2017-06-01 00:00:00"
    assert rates[0].rate == 0.0175


def test_get_rates_for_daterange_returns_empty_list_if_year_is_before_earliest_rate(notify_db, notify_db_session):
    set_up_rate(notify_db, datetime(2016, 4, 1), 0.015)
    set_up_rate(notify_db, datetime(2017, 6, 1), 0.0175)
    start_date, end_date = get_financial_year(2015)
    rates = get_rates_for_daterange(start_date, end_date, SMS_TYPE)
    assert rates == []


def test_get_rates_for_daterange_early_rate(notify_db, notify_db_session):
    set_up_rate(notify_db, datetime(2015, 6, 1), 0.014)
    set_up_rate(notify_db, datetime(2016, 6, 1), 0.015)
    set_up_rate(notify_db, datetime(2016, 9, 1), 0.016)
    set_up_rate(notify_db, datetime(2017, 6, 1), 0.0175)
    start_date, end_date = get_financial_year(2016)
    rates = get_rates_for_daterange(start_date, end_date, SMS_TYPE)
    assert len(rates) == 3


def test_get_rates_for_daterange_edge_case(notify_db, notify_db_session):
    set_up_rate(notify_db, datetime(2016, 3, 31, 23, 00), 0.015)
    set_up_rate(notify_db, datetime(2017, 3, 31, 23, 00), 0.0175)
    start_date, end_date = get_financial_year(2016)
    rates = get_rates_for_daterange(start_date, end_date, SMS_TYPE)
    assert len(rates) == 1
    assert datetime.strftime(rates[0].valid_from, '%Y-%m-%d %H:%M:%S') == "2016-03-31 23:00:00"
    assert rates[0].rate == 0.015


def test_get_rates_for_daterange_where_daterange_is_one_month_that_falls_between_rate_valid_from(
        notify_db, notify_db_session
):
    set_up_rate(notify_db, datetime(2017, 1, 1), 0.175)
    set_up_rate(notify_db, datetime(2017, 3, 31), 0.123)
    start_date = datetime(2017, 2, 1, 00, 00, 00)
    end_date = datetime(2017, 2, 28, 23, 59, 59, 99999)
    rates = get_rates_for_daterange(start_date, end_date, SMS_TYPE)
    assert len(rates) == 1
    assert datetime.strftime(rates[0].valid_from, '%Y-%m-%d %H:%M:%S') == "2017-01-01 00:00:00"
    assert rates[0].rate == 0.175


def test_get_monthly_billing_data(notify_db, notify_db_session, sample_template, sample_email_template):
    set_up_rate(notify_db, datetime(2016, 4, 1), 0.014)
    # previous year
    create_notification(template=sample_template, created_at=datetime(2016, 3, 31), sent_at=datetime(2016, 3, 31),
                        status='sending', billable_units=1)
    # current year
    create_notification(template=sample_template, created_at=datetime(2016, 4, 2), sent_at=datetime(2016, 4, 2),
                        status='sending', billable_units=1)
    create_notification(template=sample_template, created_at=datetime(2016, 5, 18), sent_at=datetime(2016, 5, 18),
                        status='sending', billable_units=2)
    create_notification(template=sample_template, created_at=datetime(2016, 7, 22), sent_at=datetime(2016, 7, 22),
                        status='sending', billable_units=3)
    create_notification(template=sample_template, created_at=datetime(2016, 7, 22), sent_at=datetime(2016, 7, 22),
                        status='sending', billable_units=3, rate_multiplier=2)
    create_notification(template=sample_template, created_at=datetime(2016, 7, 22), sent_at=datetime(2016, 7, 22),
                        status='sending', billable_units=3, rate_multiplier=2)
    create_notification(template=sample_template, created_at=datetime(2016, 7, 30), sent_at=datetime(2016, 7, 22),
                        status='sending', billable_units=4)

    create_notification(template=sample_email_template, created_at=datetime(2016, 8, 22), sent_at=datetime(2016, 7, 22),
                        status='sending', billable_units=0)
    create_notification(template=sample_email_template, created_at=datetime(2016, 8, 30), sent_at=datetime(2016, 7, 22),
                        status='sending', billable_units=0)
    # next year
    create_notification(template=sample_template, created_at=datetime(2017, 3, 31, 23, 00, 00),
                        sent_at=datetime(2017, 3, 31), status='sending', billable_units=6)
    results = get_monthly_billing_data(sample_template.service_id, 2016)
    assert len(results) == 4
    # (billable_units, rate_multiplier, international, type, rate)
    assert results[0] == ('April', 1, 1, False, SMS_TYPE, 0.014)
    assert results[1] == ('May', 2, 1, False, SMS_TYPE, 0.014)
    assert results[2] == ('July', 7, 1, False, SMS_TYPE, 0.014)
    assert results[3] == ('July', 6, 2, False, SMS_TYPE, 0.014)


def test_get_monthly_billing_data_with_multiple_rates(notify_db, notify_db_session, sample_template,
                                                      sample_email_template):
    set_up_rate(notify_db, datetime(2016, 4, 1), 0.014)
    set_up_rate(notify_db, datetime(2016, 6, 5), 0.0175)
    set_up_rate(notify_db, datetime(2017, 7, 5), 0.018)
    # previous year
    create_notification(template=sample_template, created_at=datetime(2016, 3, 31), sent_at=datetime(2016, 3, 31),
                        status='sending', billable_units=1)
    # current year
    create_notification(template=sample_template, created_at=datetime(2016, 4, 2), sent_at=datetime(2016, 4, 2),
                        status='sending', billable_units=1)
    create_notification(template=sample_template, created_at=datetime(2016, 5, 18), sent_at=datetime(2016, 5, 18),
                        status='sending', billable_units=2)
    create_notification(template=sample_template, created_at=datetime(2016, 6, 1), sent_at=datetime(2016, 6, 1),
                        status='sending', billable_units=3)
    create_notification(template=sample_template, created_at=datetime(2016, 6, 15), sent_at=datetime(2016, 6, 15),
                        status='sending', billable_units=4)
    create_notification(template=sample_email_template, created_at=datetime(2016, 8, 22),
                        sent_at=datetime(2016, 7, 22),
                        status='sending', billable_units=0)
    create_notification(template=sample_email_template, created_at=datetime(2016, 8, 30),
                        sent_at=datetime(2016, 7, 22),
                        status='sending', billable_units=0)
    # next year
    create_notification(template=sample_template, created_at=datetime(2017, 3, 31, 23, 00, 00),
                        sent_at=datetime(2017, 3, 31), status='sending', billable_units=6)
    results = get_monthly_billing_data(sample_template.service_id, 2016)
    assert len(results) == 4
    assert results[0] == ('April', 1, 1, False, SMS_TYPE, 0.014)
    assert results[1] == ('May', 2, 1, False, SMS_TYPE, 0.014)
    assert results[2] == ('June', 3, 1, False, SMS_TYPE, 0.014)
    assert results[3] == ('June', 4, 1, False, SMS_TYPE, 0.0175)


def test_get_monthly_billing_data_with_no_notifications_for_daterange(notify_db, notify_db_session, sample_template):
    set_up_rate(notify_db, datetime(2016, 4, 1), 0.014)
    results = get_monthly_billing_data(sample_template.service_id, 2016)
    assert results == []


def set_up_rate(notify_db, start_date, value):
    rate = Rate(id=uuid.uuid4(), valid_from=start_date, rate=value, notification_type=SMS_TYPE)
    notify_db.session.add(rate)


@freeze_time("2016-05-01")
def test_get_billing_data_for_month_where_start_date_before_rate_returns_empty(
    sample_template
):
    create_rate(datetime(2016, 4, 1), 0.014, SMS_TYPE)

    results = get_monthly_billing_data(
        service_id=sample_template.service_id,
        year=2015
    )

    assert not results


@freeze_time("2016-05-01")
def test_get_monthly_billing_data_where_start_date_before_rate_returns_empty(
    sample_template
):
    now = datetime.utcnow()
    create_rate(now, 0.014, SMS_TYPE)

    results = get_billing_data_for_month(
        service_id=sample_template.service_id,
        start_date=now - timedelta(days=2),
        end_date=now - timedelta(days=1),
        notification_type=SMS_TYPE
    )

    assert not results


def test_billing_letter_data_per_month_query(
        notify_db_session
):
    rate = create_letter_rate()
    service = create_service()
    template = create_template(service=service, template_type='letter')
    create_notification(template=template, billable_units=1, created_at=datetime(2017, 2, 1, 13, 21),
                        status='delivered')
    create_notification(template=template, billable_units=1, created_at=datetime(2017, 2, 1, 13, 21),
                        status='delivered')
    create_notification(template=template, billable_units=1, created_at=datetime(2017, 2, 1, 13, 21),
                        status='delivered')

    results = billing_letter_data_per_month_query(service_id=service.id,
                                                  start_date=datetime(2017, 2, 1),
                                                  end_date=datetime(2017, 2, 28))

    assert len(results) == 1
    assert results[0].rate == Decimal('0.31')
