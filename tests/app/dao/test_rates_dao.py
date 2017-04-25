from datetime import datetime

from decimal import Decimal

from app.dao.rates_dao import get_rate_for_type_and_date


def test_get_rate_for_type_and_date(notify_db):
    rate = get_rate_for_type_and_date('sms', datetime.utcnow())
    assert rate.rate == Decimal("1.58")

    rate = get_rate_for_type_and_date('sms', datetime(2016, 6, 1))
    assert rate.rate == Decimal("1.65")


def test_get_rate_for_type_and_date_early_date(notify_db):
    rate = get_rate_for_type_and_date('sms', datetime(2014, 6, 1))
    assert not rate
