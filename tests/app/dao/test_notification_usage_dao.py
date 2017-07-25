import uuid
from datetime import datetime, timedelta

import pytest
from flask import current_app

from app.dao.date_util import get_financial_year
from app.dao.notification_usage_dao import (
    get_rates_for_daterange,
    get_yearly_billing_data,
    get_monthly_billing_data,
    get_total_billable_units_for_sent_sms_notifications_in_date_range,
    discover_rate_bounds_for_billing_query
)
from app.models import (
    Rate,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_STATUS_TYPES_BILLABLE,
    NOTIFICATION_STATUS_TYPES_NON_BILLABLE)
from tests.app.conftest import sample_notification, sample_email_template, sample_letter_template, sample_service
from tests.app.db import create_notification
from freezegun import freeze_time

from tests.conftest import set_config


def test_get_rates_for_daterange(notify_db, notify_db_session):
    set_up_rate(notify_db, datetime(2016, 5, 18), 0.016)
    set_up_rate(notify_db, datetime(2017, 3, 31, 23), 0.0158)
    start_date, end_date = get_financial_year(2017)
    rates = get_rates_for_daterange(start_date, end_date, 'sms')
    assert len(rates) == 1
    assert datetime.strftime(rates[0].valid_from, '%Y-%m-%d %H:%M:%S') == "2017-03-31 23:00:00"
    assert rates[0].rate == 0.0158


def test_get_rates_for_daterange_multiple_result_per_year(notify_db, notify_db_session):
    set_up_rate(notify_db, datetime(2016, 4, 1), 0.015)
    set_up_rate(notify_db, datetime(2016, 5, 18), 0.016)
    set_up_rate(notify_db, datetime(2017, 4, 1), 0.0158)
    start_date, end_date = get_financial_year(2016)
    rates = get_rates_for_daterange(start_date, end_date, 'sms')
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
    rates_2017 = get_rates_for_daterange(start_date, end_date, 'sms')
    assert len(rates_2017) == 2
    assert datetime.strftime(rates_2017[0].valid_from, '%Y-%m-%d %H:%M:%S') == "2016-09-01 00:00:00"
    assert rates_2017[0].rate == 0.016
    assert datetime.strftime(rates_2017[1].valid_from, '%Y-%m-%d %H:%M:%S') == "2017-06-01 00:00:00"
    assert rates_2017[1].rate == 0.0175


def test_get_rates_for_daterange_in_the_future(notify_db, notify_db_session):
    set_up_rate(notify_db, datetime(2016, 4, 1), 0.015)
    set_up_rate(notify_db, datetime(2017, 6, 1), 0.0175)
    start_date, end_date = get_financial_year(2018)
    rates = get_rates_for_daterange(start_date, end_date, 'sms')
    assert datetime.strftime(rates[0].valid_from, '%Y-%m-%d %H:%M:%S') == "2017-06-01 00:00:00"
    assert rates[0].rate == 0.0175


def test_get_rates_for_daterange_returns_empty_list_if_year_is_before_earliest_rate(notify_db, notify_db_session):
    set_up_rate(notify_db, datetime(2016, 4, 1), 0.015)
    set_up_rate(notify_db, datetime(2017, 6, 1), 0.0175)
    start_date, end_date = get_financial_year(2015)
    rates = get_rates_for_daterange(start_date, end_date, 'sms')
    assert rates == []


def test_get_rates_for_daterange_early_rate(notify_db, notify_db_session):
    set_up_rate(notify_db, datetime(2015, 6, 1), 0.014)
    set_up_rate(notify_db, datetime(2016, 6, 1), 0.015)
    set_up_rate(notify_db, datetime(2016, 9, 1), 0.016)
    set_up_rate(notify_db, datetime(2017, 6, 1), 0.0175)
    start_date, end_date = get_financial_year(2016)
    rates = get_rates_for_daterange(start_date, end_date, 'sms')
    assert len(rates) == 3


def test_get_rates_for_daterange_edge_case(notify_db, notify_db_session):
    set_up_rate(notify_db, datetime(2016, 3, 31, 23, 00), 0.015)
    set_up_rate(notify_db, datetime(2017, 3, 31, 23, 00), 0.0175)
    start_date, end_date = get_financial_year(2016)
    rates = get_rates_for_daterange(start_date, end_date, 'sms')
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
    rates = get_rates_for_daterange(start_date, end_date, 'sms')
    assert len(rates) == 1
    assert datetime.strftime(rates[0].valid_from, '%Y-%m-%d %H:%M:%S') == "2017-01-01 00:00:00"
    assert rates[0].rate == 0.175


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


def test_get_monthly_billing_data_with_no_notifications_for_daterange(notify_db, notify_db_session, sample_template):
    set_up_rate(notify_db, datetime(2016, 4, 1), 0.014)
    results = get_monthly_billing_data(sample_template.service_id, 2016)
    assert len(results) == 0


def set_up_rate(notify_db, start_date, value):
    rate = Rate(id=uuid.uuid4(), valid_from=start_date, rate=value, notification_type='sms')
    notify_db.session.add(rate)


@freeze_time("2016-01-10 12:00:00.000000")
def test_returns_total_billable_units_for_sms_notifications(notify_db, notify_db_session, sample_service):
    with set_config(current_app, 'FREE_SMS_TIER_FRAGMENT_COUNT', 0):

        set_up_rate(notify_db, datetime(2016, 1, 1), 0.016)

        sample_notification(
            notify_db, notify_db_session, service=sample_service, billable_units=1, status=NOTIFICATION_DELIVERED)
        sample_notification(
            notify_db, notify_db_session, service=sample_service, billable_units=2, status=NOTIFICATION_DELIVERED)
        sample_notification(
            notify_db, notify_db_session, service=sample_service, billable_units=3, status=NOTIFICATION_DELIVERED)
        sample_notification(
            notify_db, notify_db_session, service=sample_service, billable_units=4, status=NOTIFICATION_DELIVERED)

        start = datetime.utcnow() - timedelta(minutes=10)
        end = datetime.utcnow() + timedelta(minutes=10)

        assert get_total_billable_units_for_sent_sms_notifications_in_date_range(
            start, end, sample_service.id)[0] == 10
        assert get_total_billable_units_for_sent_sms_notifications_in_date_range(
            start, end, sample_service.id)[1] == 0.16


@freeze_time("2016-01-10 12:00:00.000000")
def test_returns_total_billable_units_multiplied_by_multipler_for_sms_notifications(
        notify_db, notify_db_session, sample_service
):
    with set_config(current_app, 'FREE_SMS_TIER_FRAGMENT_COUNT', 0):
        set_up_rate(notify_db, datetime(2016, 1, 1), 2.5)

        sample_notification(
            notify_db, notify_db_session, service=sample_service, rate_multiplier=1.0, status=NOTIFICATION_DELIVERED)
        sample_notification(
            notify_db, notify_db_session, service=sample_service, rate_multiplier=2.0, status=NOTIFICATION_DELIVERED)
        sample_notification(
            notify_db, notify_db_session, service=sample_service, rate_multiplier=5.0, status=NOTIFICATION_DELIVERED)
        sample_notification(
            notify_db, notify_db_session, service=sample_service, rate_multiplier=10.0, status=NOTIFICATION_DELIVERED)

        start = datetime.utcnow() - timedelta(minutes=10)
        end = datetime.utcnow() + timedelta(minutes=10)

        assert get_total_billable_units_for_sent_sms_notifications_in_date_range(start, end, sample_service.id)[0] == 18
        assert get_total_billable_units_for_sent_sms_notifications_in_date_range(start, end, sample_service.id)[1] == 45


def test_returns_total_billable_units_multiplied_by_multipler_for_sms_notifications_for_several_rates(
        notify_db, notify_db_session, sample_service
):
    with set_config(current_app, 'FREE_SMS_TIER_FRAGMENT_COUNT', 0):

        set_up_rate(notify_db, datetime(2016, 1, 1), 2)
        set_up_rate(notify_db, datetime(2016, 10, 1), 4)
        set_up_rate(notify_db, datetime(2017, 1, 1), 6)

        eligble_rate_1 = datetime(2016, 2, 1)
        eligble_rate_2 = datetime(2016, 11, 1)
        eligble_rate_3 = datetime(2017, 2, 1)

        sample_notification(
            notify_db,
            notify_db_session,
            service=sample_service,
            rate_multiplier=1.0,
            status=NOTIFICATION_DELIVERED,
            created_at=eligble_rate_1)

        sample_notification(
            notify_db,
            notify_db_session,
            service=sample_service,
            rate_multiplier=2.0,
            status=NOTIFICATION_DELIVERED,
            created_at=eligble_rate_2)

        sample_notification(
            notify_db,
            notify_db_session,
            service=sample_service,
            rate_multiplier=5.0,
            status=NOTIFICATION_DELIVERED,
            created_at=eligble_rate_3)

        start = datetime(2016, 1, 1)
        end = datetime(2018, 1, 1)
        assert get_total_billable_units_for_sent_sms_notifications_in_date_range(start, end, sample_service.id)[0] == 8
        assert get_total_billable_units_for_sent_sms_notifications_in_date_range(start, end, sample_service.id)[1] == 40


def test_returns_total_billable_units_for_sms_notifications_for_several_rates_where_dates_match_rate_boundary(
        notify_db, notify_db_session, sample_service
):
    with set_config(current_app, 'FREE_SMS_TIER_FRAGMENT_COUNT', 0):

        set_up_rate(notify_db, datetime(2016, 1, 1), 2)
        set_up_rate(notify_db, datetime(2016, 10, 1), 4)
        set_up_rate(notify_db, datetime(2017, 1, 1), 6)

        eligble_rate_1_start = datetime(2016, 1, 1, 0, 0, 0, 0)
        eligble_rate_1_end = datetime(2016, 9, 30, 23, 59, 59, 999)
        eligble_rate_2_start = datetime(2016, 10, 1, 0, 0, 0, 0)
        eligble_rate_2_end = datetime(2016, 12, 31, 23, 59, 59, 999)
        eligble_rate_3_start = datetime(2017, 1, 1, 0, 0, 0, 0)
        eligble_rate_3_whenever = datetime(2017, 12, 12, 0, 0, 0, 0)

        def make_notification(created_at):
            sample_notification(
                notify_db,
                notify_db_session,
                service=sample_service,
                rate_multiplier=1.0,
                status=NOTIFICATION_DELIVERED,
                created_at=created_at)

        make_notification(eligble_rate_1_start)
        make_notification(eligble_rate_1_end)
        make_notification(eligble_rate_2_start)
        make_notification(eligble_rate_2_end)
        make_notification(eligble_rate_3_start)
        make_notification(eligble_rate_3_whenever)

        start = datetime(2016, 1, 1)
        end = datetime(2018, 1, 1)

        assert get_total_billable_units_for_sent_sms_notifications_in_date_range(
            start, end, sample_service.id)[0] == 6
        assert get_total_billable_units_for_sent_sms_notifications_in_date_range(
            start, end, sample_service.id)[1] == 24.0


@freeze_time("2016-01-10 12:00:00.000000")
def test_returns_total_billable_units_for_sms_notifications_ignoring_letters_and_emails(
        notify_db, notify_db_session, sample_service
):
    with set_config(current_app, 'FREE_SMS_TIER_FRAGMENT_COUNT', 0):

        set_up_rate(notify_db, datetime(2016, 1, 1), 2.5)

        email_template = sample_email_template(notify_db, notify_db_session, service=sample_service)
        letter_template = sample_letter_template(sample_service)

        sample_notification(
            notify_db,
            notify_db_session,
            service=sample_service,
            billable_units=2,
            status=NOTIFICATION_DELIVERED)
        sample_notification(
            notify_db,
            notify_db_session,
            template=email_template,
            service=sample_service,
            billable_units=2,
            status=NOTIFICATION_DELIVERED)
        sample_notification(
            notify_db,
            notify_db_session,
            template=letter_template,
            service=sample_service,
            billable_units=2,
            status=NOTIFICATION_DELIVERED
        )

        start = datetime.utcnow() - timedelta(minutes=10)
        end = datetime.utcnow() + timedelta(minutes=10)

        assert get_total_billable_units_for_sent_sms_notifications_in_date_range(start, end, sample_service.id)[0] == 2
        assert get_total_billable_units_for_sent_sms_notifications_in_date_range(start, end, sample_service.id)[1] == 5


@freeze_time("2016-01-10 12:00:00.000000")
def test_returns_total_billable_units_for_sms_notifications_for_only_requested_service(
        notify_db, notify_db_session
):
    with set_config(current_app, 'FREE_SMS_TIER_FRAGMENT_COUNT', 0):

        set_up_rate(notify_db, datetime(2016, 1, 1), 2.5)

        service_1 = sample_service(notify_db, notify_db_session, service_name=str(uuid.uuid4()))
        service_2 = sample_service(notify_db, notify_db_session, service_name=str(uuid.uuid4()))
        service_3 = sample_service(notify_db, notify_db_session, service_name=str(uuid.uuid4()))

        sample_notification(
            notify_db,
            notify_db_session,
            service=service_1,
            billable_units=2,
            status=NOTIFICATION_DELIVERED)
        sample_notification(
            notify_db,
            notify_db_session,
            service=service_2,
            billable_units=2,
            status=NOTIFICATION_DELIVERED)
        sample_notification(
            notify_db,
            notify_db_session,
            service=service_3,
            billable_units=2,
            status=NOTIFICATION_DELIVERED
        )

        start = datetime.utcnow() - timedelta(minutes=10)
        end = datetime.utcnow() + timedelta(minutes=10)

        assert get_total_billable_units_for_sent_sms_notifications_in_date_range(start, end, service_1.id)[0] == 2
        assert get_total_billable_units_for_sent_sms_notifications_in_date_range(start, end, service_1.id)[1] == 5


@freeze_time("2016-01-10 12:00:00.000000")
def test_returns_total_billable_units_for_sms_notifications_handling_null_values(
    notify_db, notify_db_session, sample_service
):
    with set_config(current_app, 'FREE_SMS_TIER_FRAGMENT_COUNT', 0):

        set_up_rate(notify_db, datetime(2016, 1, 1), 2.5)

        sample_notification(
            notify_db,
            notify_db_session,
            service=sample_service,
            billable_units=2,
            rate_multiplier=None,
            status=NOTIFICATION_DELIVERED)

        start = datetime.utcnow() - timedelta(minutes=10)
        end = datetime.utcnow() + timedelta(minutes=10)

        assert get_total_billable_units_for_sent_sms_notifications_in_date_range(start, end, sample_service.id)[0] == 2
        assert get_total_billable_units_for_sent_sms_notifications_in_date_range(start, end, sample_service.id)[1] == 5


@pytest.mark.parametrize('billable_units, states', ([
    (len(NOTIFICATION_STATUS_TYPES_BILLABLE), NOTIFICATION_STATUS_TYPES_BILLABLE),
    (0, NOTIFICATION_STATUS_TYPES_NON_BILLABLE)
]))
@freeze_time("2016-01-10 12:00:00.000000")
def test_ignores_non_billable_states_when_returning_billable_units_for_sms_notifications(
    notify_db, notify_db_session, sample_service, billable_units, states
):
    with set_config(current_app, 'FREE_SMS_TIER_FRAGMENT_COUNT', 0):
        set_up_rate(notify_db, datetime(2016, 1, 1), 2.5)

        for state in states:
            sample_notification(
                notify_db,
                notify_db_session,
                service=sample_service,
                billable_units=1,
                rate_multiplier=None,
                status=state)

        start = datetime.utcnow() - timedelta(minutes=10)
        end = datetime.utcnow() + timedelta(minutes=10)

        assert get_total_billable_units_for_sent_sms_notifications_in_date_range(
            start, end, sample_service.id
        )[0] == billable_units
        assert get_total_billable_units_for_sent_sms_notifications_in_date_range(
            start, end, sample_service.id
        )[1] == billable_units * 2.5


@freeze_time("2016-01-10 12:00:00.000000")
def test_restricts_to_time_period_when_returning_billable_units_for_sms_notifications(
    notify_db, notify_db_session, sample_service
):
    with set_config(current_app, 'FREE_SMS_TIER_FRAGMENT_COUNT', 0):
        set_up_rate(notify_db, datetime(2016, 1, 1), 2.5)

        sample_notification(
            notify_db,
            notify_db_session,
            service=sample_service,
            billable_units=1,
            rate_multiplier=1.0,
            created_at=datetime.utcnow() - timedelta(minutes=100),
            status=NOTIFICATION_DELIVERED)

        sample_notification(
            notify_db,
            notify_db_session,
            service=sample_service,
            billable_units=1,
            rate_multiplier=1.0,
            created_at=datetime.utcnow() - timedelta(minutes=5),
            status=NOTIFICATION_DELIVERED)

        start = datetime.utcnow() - timedelta(minutes=10)
        end = datetime.utcnow() + timedelta(minutes=10)

        assert get_total_billable_units_for_sent_sms_notifications_in_date_range(
            start, end, sample_service.id)[0] == 1
        assert get_total_billable_units_for_sent_sms_notifications_in_date_range(
            start, end, sample_service.id)[1] == 2.5


def test_returns_zero_if_no_matching_rows_when_returning_billable_units_for_sms_notifications(
        notify_db, notify_db_session, sample_service
):
    set_up_rate(notify_db, datetime(2016, 1, 1), 2.5)

    start = datetime.utcnow() - timedelta(minutes=10)
    end = datetime.utcnow() + timedelta(minutes=10)
    assert get_total_billable_units_for_sent_sms_notifications_in_date_range(start, end, sample_service.id)[0] == 0
    assert get_total_billable_units_for_sent_sms_notifications_in_date_range(start, end, sample_service.id)[1] == 0.0


def test_should_calculate_rate_boundaries_for_billing_query_for_single_relevant_rate(notify_db, notify_db_session):
    start_date, end_date = get_financial_year(2016)
    set_up_rate(notify_db, datetime(2016, 1, 1), 0.016)
    rate_boundaries = discover_rate_bounds_for_billing_query(start_date, end_date)
    assert len(rate_boundaries) == 1
    assert rate_boundaries[0]['start_date'] == start_date
    assert rate_boundaries[0]['end_date'] == end_date
    assert rate_boundaries[0]['rate'] == 0.016


def test_should_calculate_rate_boundaries_for_billing_query_for_two_relevant_rates(notify_db, notify_db_session):
    start_date, end_date = get_financial_year(2016)

    rate_1_valid_from = datetime(2016, 1, 1)
    rate_2_valid_from = datetime(2017, 1, 1)

    set_up_rate(notify_db, rate_1_valid_from, 0.02)
    set_up_rate(notify_db, rate_2_valid_from, 0.04)
    rate_boundaries = discover_rate_bounds_for_billing_query(start_date, end_date)
    assert len(rate_boundaries) == 2
    assert rate_boundaries[0]['start_date'] == start_date
    assert rate_boundaries[0]['end_date'] == rate_2_valid_from
    assert rate_boundaries[0]['rate'] == 0.02

    assert rate_boundaries[1]['start_date'] == rate_2_valid_from
    assert rate_boundaries[1]['end_date'] == end_date
    assert rate_boundaries[1]['rate'] == 0.04


def test_should_calculate_rate_boundaries_for_billing_query_for_three_relevant_rates(notify_db, notify_db_session):
    start_date, end_date = get_financial_year(2016)
    rate_1_valid_from = datetime(2016, 1, 1)
    rate_2_valid_from = datetime(2017, 1, 1)
    rate_3_valid_from = datetime(2017, 2, 1)

    set_up_rate(notify_db, rate_1_valid_from, 0.02)
    set_up_rate(notify_db, rate_2_valid_from, 0.04)
    set_up_rate(notify_db, rate_3_valid_from, 0.06)
    rate_boundaries = discover_rate_bounds_for_billing_query(start_date, end_date)
    assert len(rate_boundaries) == 3

    assert rate_boundaries[0]['start_date'] == start_date
    assert rate_boundaries[0]['end_date'] == rate_2_valid_from
    assert rate_boundaries[0]['rate'] == 0.02

    assert rate_boundaries[1]['start_date'] == rate_2_valid_from
    assert rate_boundaries[1]['end_date'] == rate_3_valid_from
    assert rate_boundaries[1]['rate'] == 0.04

    assert rate_boundaries[2]['start_date'] == rate_3_valid_from
    assert rate_boundaries[2]['end_date'] == end_date
    assert rate_boundaries[2]['rate'] == 0.06


@freeze_time("2016-01-10 12:00:00.000000")
def test_deducts_free_tier_from_bill(
        notify_db, notify_db_session
):
    start_value = current_app.config['FREE_SMS_TIER_FRAGMENT_COUNT']
    try:
        current_app.config['FREE_SMS_TIER_FRAGMENT_COUNT'] = 1

        set_up_rate(notify_db, datetime(2016, 1, 1), 2.5)

        service_1 = sample_service(notify_db, notify_db_session, service_name=str(uuid.uuid4()))

        sample_notification(
            notify_db,
            notify_db_session,
            service=service_1,
            billable_units=1,
            status=NOTIFICATION_DELIVERED)
        sample_notification(
            notify_db,
            notify_db_session,
            service=service_1,
            billable_units=1,
            status=NOTIFICATION_DELIVERED)

        start = datetime.utcnow() - timedelta(minutes=10)
        end = datetime.utcnow() + timedelta(minutes=10)

        assert get_total_billable_units_for_sent_sms_notifications_in_date_range(start, end, service_1.id)[0] == 2
        assert get_total_billable_units_for_sent_sms_notifications_in_date_range(start, end, service_1.id)[1] == 2.5
    finally:
        current_app.config['FREE_SMS_TIER_FRAGMENT_COUNT'] = start_value


@freeze_time("2016-01-10 12:00:00.000000")
@pytest.mark.parametrize(
    'free_tier, expected_cost',
    [(0, 24.0), (1, 22.0), (2, 20.0), (3, 16.0), (4, 12.0), (5, 6.0), (6, 0.0)]
)
def test_deducts_free_tier_from_bill_across_rate_boundaries(
        notify_db, notify_db_session, sample_service, free_tier, expected_cost
):
    start_value = current_app.config['FREE_SMS_TIER_FRAGMENT_COUNT']
    try:
        current_app.config['FREE_SMS_TIER_FRAGMENT_COUNT'] = free_tier
        set_up_rate(notify_db, datetime(2016, 1, 1), 2)
        set_up_rate(notify_db, datetime(2016, 10, 1), 4)
        set_up_rate(notify_db, datetime(2017, 1, 1), 6)

        eligble_rate_1_start = datetime(2016, 1, 1, 0, 0, 0, 0)
        eligble_rate_1_end = datetime(2016, 9, 30, 23, 59, 59, 999)
        eligble_rate_2_start = datetime(2016, 10, 1, 0, 0, 0, 0)
        eligble_rate_2_end = datetime(2016, 12, 31, 23, 59, 59, 999)
        eligble_rate_3_start = datetime(2017, 1, 1, 0, 0, 0, 0)
        eligble_rate_3_whenever = datetime(2017, 12, 12, 0, 0, 0, 0)

        def make_notification(created_at):
            sample_notification(
                notify_db,
                notify_db_session,
                service=sample_service,
                rate_multiplier=1.0,
                status=NOTIFICATION_DELIVERED,
                created_at=created_at)

        make_notification(eligble_rate_1_start)
        make_notification(eligble_rate_1_end)
        make_notification(eligble_rate_2_start)
        make_notification(eligble_rate_2_end)
        make_notification(eligble_rate_3_start)
        make_notification(eligble_rate_3_whenever)

        start = datetime(2016, 1, 1)
        end = datetime(2018, 1, 1)

        assert get_total_billable_units_for_sent_sms_notifications_in_date_range(start, end, sample_service.id)[0] == 6
        assert get_total_billable_units_for_sent_sms_notifications_in_date_range(
            start, end, sample_service.id
        )[1] == expected_cost
    finally:
        current_app.config['FREE_SMS_TIER_FRAGMENT_COUNT'] = start_value
