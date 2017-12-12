from datetime import datetime

from decimal import Decimal

from app.dao.letter_rate_dao import dao_create_letter_rate, get_letter_rates_for_daterange
from app.models import LetterRate


def test_dao_create_letter_rate(notify_db_session):
    letter_rate = LetterRate(start_date=datetime(2017, 12, 1),
                             rate=0.33,
                             crown=True,
                             sheet_count=1,
                             post_class='second')

    dao_create_letter_rate(letter_rate)

    rates = LetterRate.query.all()
    assert len(rates) == 1


def test_get_letter_rates_for_daterange(notify_db_session):
    letter_rate = LetterRate(start_date=datetime(2017, 12, 1),
                             rate=0.33,
                             crown=True,
                             sheet_count=1,
                             post_class='second')

    dao_create_letter_rate(letter_rate)
    letter_rate = LetterRate(start_date=datetime(2016, 12, 1),
                             end_date=datetime(2017, 12, 1),
                             rate=0.30,
                             crown=True,
                             sheet_count=1,
                             post_class='second')

    dao_create_letter_rate(letter_rate)

    results = get_letter_rates_for_daterange(date=datetime(2017, 12, 2), crown=True, sheet_count=1, post_class='second')
    assert len(results) == 1
    assert results[0].rate == Decimal('0.33')
