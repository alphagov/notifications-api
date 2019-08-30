from datetime import datetime, date

import pytest

from app.dao.date_util import (
    get_financial_year,
    get_april_fools,
    get_month_start_and_end_date_in_utc,
    get_financial_year_for_datetime,
)


def test_get_financial_year():
    start, end = get_financial_year(2000)
    assert str(start) == '2000-03-31 23:00:00'
    assert str(end) == '2001-03-31 22:59:59.999999'


def test_get_april_fools():
    april_fools = get_april_fools(2016)
    assert str(april_fools) == '2016-03-31 23:00:00'
    assert april_fools.tzinfo is None


@pytest.mark.parametrize("month, year, expected_start, expected_end", [
    (7, 2017, datetime(2017, 6, 30, 23, 00, 00), datetime(2017, 7, 31, 22, 59, 59, 99999)),
    (2, 2016, datetime(2016, 2, 1, 00, 00, 00), datetime(2016, 2, 29, 23, 59, 59, 99999)),
    (2, 2017, datetime(2017, 2, 1, 00, 00, 00), datetime(2017, 2, 28, 23, 59, 59, 99999)),
    (9, 2018, datetime(2018, 8, 31, 23, 00, 00), datetime(2018, 9, 30, 22, 59, 59, 99999)),
    (12, 2019, datetime(2019, 12, 1, 00, 00, 00), datetime(2019, 12, 31, 23, 59, 59, 99999))
])
def test_get_month_start_and_end_date_in_utc(month, year, expected_start, expected_end):
    month_year = datetime(year, month, 10, 13, 30, 00)
    result = get_month_start_and_end_date_in_utc(month_year)
    assert result[0] == expected_start
    assert result[1] == expected_end


@pytest.mark.parametrize("dt, fy", [
    (datetime(2018, 3, 31, 23, 0, 0), 2018),
    (datetime(2019, 3, 31, 22, 59, 59), 2018),
    (datetime(2019, 3, 31, 23, 0, 0), 2019),
    (date(2019, 3, 31), 2018),
    (date(2019, 4, 1), 2019),
])
def test_get_financial_year_for_datetime(dt, fy):
    assert get_financial_year_for_datetime(dt) == fy
