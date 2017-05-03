import uuid
from datetime import datetime

from app.dao.date_util import get_financial_year
from app.dao.notification_usage_dao import (get_rates_for_year, get_yearly_billing_data,
                                            get_monthly_billing_data)
from app.models import Rate
from tests.app.db import create_notification


def test_get_rates_for_year(notify_db, notify_db_session):
    set_up_rate(notify_db, datetime(2016, 5, 18), 0.016)
    set_up_rate(notify_db, datetime(2017, 3, 31, 23), 0.0158)
    start_date, end_date = get_financial_year(2017)
    print(start_date)
    rates = get_rates_for_year(start_date, end_date, 'sms')
    assert len(rates) == 1
    assert datetime.strftime(rates[0].valid_from, '%Y-%m-%d %H:%M:%S') == "2017-03-31 23:00:00"
    assert rates[0].rate == 0.0158


def test_get_rates_for_year_multiple_result_per_year(notify_db, notify_db_session):
    set_up_rate(notify_db, datetime(2016, 4, 1), 0.015)
    set_up_rate(notify_db, datetime(2016, 5, 18), 0.016)
    set_up_rate(notify_db, datetime(2017, 4, 1), 0.0158)
    start_date, end_date = get_financial_year(2016)
    rates = get_rates_for_year(start_date, end_date, 'sms')
    assert len(rates) == 2
    assert datetime.strftime(rates[0].valid_from, '%Y-%m-%d %H:%M:%S') == "2016-04-01 00:00:00"
    assert rates[0].rate == 0.015
    assert datetime.strftime(rates[1].valid_from, '%Y-%m-%d %H:%M:%S') == "2016-05-18 00:00:00"
    assert rates[1].rate == 0.016


def test_get_rates_for_year_returns_correct_rates(notify_db, notify_db_session):
    set_up_rate(notify_db, datetime(2016, 4, 1), 0.015)
    set_up_rate(notify_db, datetime(2016, 9, 1), 0.016)
    set_up_rate(notify_db, datetime(2017, 6, 1), 0.0175)
    start_date, end_date = get_financial_year(2017)
    rates_2017 = get_rates_for_year(start_date, end_date, 'sms')
    assert len(rates_2017) == 2
    assert datetime.strftime(rates_2017[0].valid_from, '%Y-%m-%d %H:%M:%S') == "2016-09-01 00:00:00"
    assert rates_2017[0].rate == 0.016
    assert datetime.strftime(rates_2017[1].valid_from, '%Y-%m-%d %H:%M:%S') == "2017-06-01 00:00:00"
    assert rates_2017[1].rate == 0.0175


def test_get_rates_for_year_in_the_future(notify_db, notify_db_session):
    set_up_rate(notify_db, datetime(2016, 4, 1), 0.015)
    set_up_rate(notify_db, datetime(2017, 6, 1), 0.0175)
    start_date, end_date = get_financial_year(2018)
    rates = get_rates_for_year(start_date, end_date, 'sms')
    assert datetime.strftime(rates[0].valid_from, '%Y-%m-%d %H:%M:%S') == "2017-06-01 00:00:00"
    assert rates[0].rate == 0.0175


def test_get_rates_for_year_returns_empty_list_if_year_is_before_earliest_rate(notify_db, notify_db_session):
    set_up_rate(notify_db, datetime(2016, 4, 1), 0.015)
    set_up_rate(notify_db, datetime(2017, 6, 1), 0.0175)
    start_date, end_date = get_financial_year(2015)
    rates = get_rates_for_year(start_date, end_date, 'sms')
    assert rates == []


def test_get_rates_for_year_early_rate(notify_db, notify_db_session):
    set_up_rate(notify_db, datetime(2015, 6, 1), 0.014)
    set_up_rate(notify_db, datetime(2016, 6, 1), 0.015)
    set_up_rate(notify_db, datetime(2016, 9, 1), 0.016)
    set_up_rate(notify_db, datetime(2017, 6, 1), 0.0175)
    start_date, end_date = get_financial_year(2016)
    rates = get_rates_for_year(start_date, end_date, 'sms')
    assert len(rates) == 3


def test_get_rates_for_year_edge_case(notify_db, notify_db_session):
    set_up_rate(notify_db, datetime(2016, 3, 31, 23, 00), 0.015)
    set_up_rate(notify_db, datetime(2017, 3, 31, 23, 00), 0.0175)
    start_date, end_date = get_financial_year(2016)
    rates = get_rates_for_year(start_date, end_date, 'sms')
    assert len(rates) == 1
    assert datetime.strftime(rates[0].valid_from, '%Y-%m-%d %H:%M:%S') == "2016-03-31 23:00:00"
    assert rates[0].rate == 0.015


def test_get_yearly_billing_data(notify_db, notify_db_session, sample_template, sample_email_template):
    set_up_rate(notify_db, datetime(2016, 4, 1), 0.014)
    set_up_rate(notify_db, datetime(2016, 6, 1), 0.0158)
    set_up_rate(notify_db, datetime(2017, 6, 1), 0.0165)
    # previous year
    create_notification(template=sample_template, created_at=datetime(2016, 3, 31), sent_at=datetime(2016, 3, 31),
                        status='sending', billable_units=1)
    # current year
    create_notification(template=sample_template, created_at=datetime(2016, 4, 2), sent_at=datetime(2016, 4, 2),
                        status='sending', billable_units=1)
    create_notification(template=sample_template, created_at=datetime(2016, 5, 18), sent_at=datetime(2016, 5, 18),
                        status='sending', billable_units=2)
    create_notification(template=sample_template, created_at=datetime(2016, 7, 22), sent_at=datetime(2016, 7, 22),
                        status='sending', billable_units=3, rate_multiplier=2, international=True, phone_prefix="1")
    create_notification(template=sample_template, created_at=datetime(2016, 9, 15), sent_at=datetime(2016, 9, 15),
                        status='sending', billable_units=4)
    create_notification(template=sample_template, created_at=datetime(2017, 3, 31), sent_at=datetime(2017, 3, 31),
                        status='sending', billable_units=5)
    create_notification(template=sample_email_template, created_at=datetime(2016, 9, 15), sent_at=datetime(2016, 9, 15),
                        status='sending', billable_units=0)
    create_notification(template=sample_email_template, created_at=datetime(2017, 3, 31), sent_at=datetime(2017, 3, 31),
                        status='sending', billable_units=0)
    # next year
    create_notification(template=sample_template, created_at=datetime(2017, 4, 1), sent_at=datetime(2017, 4, 1),
                        status='sending', billable_units=6)
    results = get_yearly_billing_data(sample_template.service_id, 2016)
    assert len(results) == 4
    assert results[0] == (3, 3, 1, 'sms', False, 0.014)
    assert results[1] == (9, 9, 1, 'sms', False, 0.0158)
    assert results[2] == (6, 3, 2, 'sms', True, 0.0158)
    assert results[3] == (2, 2, 1, 'email', False, 0)


def test_get_future_yearly_billing_data(notify_db, notify_db_session, sample_template, sample_email_template):
    set_up_rate(notify_db, datetime(2017, 4, 1), 0.0158)

    create_notification(template=sample_template, created_at=datetime(2017, 3, 30), sent_at=datetime(2017, 3, 30),
                        status='sending', billable_units=1)
    create_notification(template=sample_template, created_at=datetime(2017, 4, 6), sent_at=datetime(2017, 4, 6),
                        status='sending', billable_units=1)
    create_notification(template=sample_template, created_at=datetime(2017, 4, 6), sent_at=datetime(2017, 4, 6),
                        status='sending', billable_units=1)

    results = get_yearly_billing_data(sample_template.service_id, 2018)
    assert len(results) == 2
    assert results[0] == (0, 0, 1, 'sms', False, 0.0158)


def test_get_yearly_billing_data_with_one_rate(notify_db, notify_db_session, sample_template):
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
    create_notification(template=sample_template, created_at=datetime(2016, 9, 15), sent_at=datetime(2016, 9, 15),
                        status='sending', billable_units=4)
    create_notification(template=sample_template, created_at=datetime(2017, 3, 31, 22, 59, 59),
                        sent_at=datetime(2017, 3, 31), status='sending', billable_units=5)
    # next year
    create_notification(template=sample_template, created_at=datetime(2017, 3, 31, 23, 00, 00),
                        sent_at=datetime(2017, 3, 31), status='sending', billable_units=6)
    create_notification(template=sample_template, created_at=datetime(2017, 4, 1), sent_at=datetime(2017, 4, 1),
                        status='sending', billable_units=7)
    results = get_yearly_billing_data(sample_template.service_id, 2016)
    assert len(results) == 2
    assert results[0] == (15, 15, 1, 'sms', False, 0.014)
    assert results[1] == (0, 0, 1, 'email', False, 0)


def test_get_yearly_billing_data_with_no_sms_notifications(notify_db, notify_db_session, sample_email_template):
    set_up_rate(notify_db, datetime(2016, 4, 1), 0.014)
    create_notification(template=sample_email_template, created_at=datetime(2016, 7, 31), sent_at=datetime(2016, 3, 31),
                        status='sending', billable_units=0)
    create_notification(template=sample_email_template, created_at=datetime(2016, 10, 2), sent_at=datetime(2016, 4, 2),
                        status='sending', billable_units=0)

    results = get_yearly_billing_data(sample_email_template.service_id, 2016)
    assert len(results) == 2
    assert results[0] == (0, 0, 1, 'sms', False, 0.014)
    assert results[1] == (2, 2, 1, 'email', False, 0)


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
    assert results[0] == ('April', 1, 1, False, 'sms', 0.014)
    assert results[1] == ('May', 2, 1, False, 'sms', 0.014)
    assert results[2] == ('July', 7, 1, False, 'sms', 0.014)
    assert results[3] == ('July', 6, 2, False, 'sms', 0.014)


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
    assert results[0] == ('April', 1, 1, False, 'sms', 0.014)
    assert results[1] == ('May', 2, 1, False, 'sms', 0.014)
    assert results[2] == ('June', 3, 1, False, 'sms', 0.014)
    assert results[3] == ('June', 4, 1, False, 'sms', 0.0175)


def test_get_monthly_billing_data_with_no_notifications_for_year(notify_db, notify_db_session, sample_template,
                                                                 sample_email_template):
    set_up_rate(notify_db, datetime(2016, 4, 1), 0.014)
    results = get_monthly_billing_data(sample_template.service_id, 2016)
    assert len(results) == 0


def set_up_rate(notify_db, start_date, value):
    rate = Rate(id=uuid.uuid4(), valid_from=start_date, rate=value, notification_type='sms')
    notify_db.session.add(rate)
