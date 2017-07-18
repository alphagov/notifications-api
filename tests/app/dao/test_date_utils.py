from datetime import datetime

import pytest

from app.dao.date_util import get_financial_year, get_april_fools, get_month_start_end_date


def test_get_financial_year():
    start, end = get_financial_year(2000)
    assert str(start) == '2000-03-31 23:00:00'
    assert str(end) == '2001-03-31 22:59:59.999999'


def test_get_april_fools():
    april_fools = get_april_fools(2016)
    assert str(april_fools) == '2016-03-31 23:00:00'
    assert april_fools.tzinfo is None


@pytest.mark.parametrize("month, year, expected_end",
                         [(7, 2017, 31),
                          (2, 2016, 29),
                          (2, 2017, 28),
                          (9, 2018, 30),
                          (12, 2019, 31)])
def test_get_month_start_end_date(month, year, expected_end):
    month_year = datetime(year, month, 10, 13, 30, 00)
    result = get_month_start_end_date(month_year)
    assert result[0] == datetime(year, month, 1, 0, 0, 0, 0)
    assert result[1] == datetime(year, month, expected_end, 23, 59, 59, 99999)
