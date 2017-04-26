import uuid
from datetime import datetime

from decimal import Decimal

from app.dao.notification_usage_dao import (get_rates_for_year, get_yearly_billing_data)
from app.models import Rate
from tests.app.db import create_notification


def test_get_rates_for_year(notify_db, notify_db_session):
    set_up_rate(notify_db, datetime(2016, 4, 1), 1.50)
    set_up_rate(notify_db, datetime(2017, 6, 1), 1.75)
    rates = get_rates_for_year(datetime(2016, 4, 1), datetime(2017, 3, 31), 'sms')
    assert len(rates) == 1
    assert datetime.strftime(rates[0].valid_from, '%Y-%m-%d %H:%M:%S') == "2016-04-01 00:00:00"
    assert rates[0].rate == Decimal("1.50")
    rates = get_rates_for_year(datetime(2017, 4, 1), datetime(2018, 3, 31), 'sms')
    assert len(rates) == 1
    assert datetime.strftime(rates[0].valid_from, '%Y-%m-%d %H:%M:%S') == "2017-06-01 00:00:00"
    assert rates[0].rate == Decimal("1.75")


def test_get_yearly_billing_data(notify_db, notify_db_session, sample_template, sample_email_template):
    set_up_rate(notify_db, datetime(2016, 4, 1), 1.40)
    set_up_rate(notify_db, datetime(2016, 6, 1), 1.58)
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
    assert len(results) == 3
    assert results[0] == (3, 'sms', Decimal('1.4'))
    assert results[1] == (12, 'sms', Decimal('1.58'))
    assert results[2] == (2, 'email', Decimal("0"))


def test_get_yearly_billing_data_with_one_rate(notify_db, notify_db_session, sample_template):
    set_up_rate(notify_db, datetime(2016, 4, 1), 1.40)
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
    assert results[0] == (15, 'sms', Decimal('1.4'))
    assert results[1] == (0, 'email', Decimal('0'))


def test_get_yearly_billing_data_with_no_sms_notifications(notify_db, notify_db_session, sample_email_template):
    set_up_rate(notify_db, datetime(2016, 4, 1), 1.40)
    create_notification(template=sample_email_template, created_at=datetime(2016, 7, 31), sent_at=datetime(2016, 3, 31),
                        status='sending', billable_units=0)
    create_notification(template=sample_email_template, created_at=datetime(2016, 10, 2), sent_at=datetime(2016, 4, 2),
                        status='sending', billable_units=0)

    results = get_yearly_billing_data(sample_email_template.service_id, 2016)
    assert len(results) == 2
    assert results[0] == (0, 'sms', Decimal('0'))
    assert results[1] == (2, 'email', Decimal('0'))


def set_up_rate(notify_db, start_date, value):
    rate = Rate(id=uuid.uuid4(), valid_from=start_date, rate=value, notification_type='sms')
    notify_db.session.add(rate)
