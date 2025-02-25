from datetime import date, datetime

import pytest

from app.dao.date_util import (
    get_april_fools,
    get_financial_year,
    get_financial_year_for_datetime,
    get_month_start_and_end_date_in_utc,
    parse_date_range,
)


def test_get_financial_year():
    start, end = get_financial_year(2000)
    assert str(start) == "2000-03-31 23:00:00"
    assert str(end) == "2001-03-31 22:59:59.999999"


def test_get_april_fools():
    april_fools = get_april_fools(2016)
    assert str(april_fools) == "2016-03-31 23:00:00"
    assert april_fools.tzinfo is None


@pytest.mark.parametrize(
    "month, year, expected_start, expected_end",
    [
        (7, 2017, datetime(2017, 6, 30, 23, 00, 00), datetime(2017, 7, 31, 22, 59, 59, 99999)),
        (2, 2016, datetime(2016, 2, 1, 00, 00, 00), datetime(2016, 2, 29, 23, 59, 59, 99999)),
        (2, 2017, datetime(2017, 2, 1, 00, 00, 00), datetime(2017, 2, 28, 23, 59, 59, 99999)),
        (9, 2018, datetime(2018, 8, 31, 23, 00, 00), datetime(2018, 9, 30, 22, 59, 59, 99999)),
        (12, 2019, datetime(2019, 12, 1, 00, 00, 00), datetime(2019, 12, 31, 23, 59, 59, 99999)),
    ],
)
def test_get_month_start_and_end_date_in_utc(month, year, expected_start, expected_end):
    month_year = datetime(year, month, 10, 13, 30, 00)
    result = get_month_start_and_end_date_in_utc(month_year)
    assert result[0] == expected_start
    assert result[1] == expected_end


@pytest.mark.parametrize(
    "dt, fy",
    [
        (datetime(2018, 3, 31, 23, 0, 0), 2018),
        (datetime(2019, 3, 31, 22, 59, 59), 2018),
        (datetime(2019, 3, 31, 23, 0, 0), 2019),
        (date(2019, 3, 31), 2018),
        (date(2019, 4, 1), 2019),
    ],
)
def test_get_financial_year_for_datetime(dt, fy):
    assert get_financial_year_for_datetime(dt) == fy


@pytest.mark.parametrize(
    "date_str, is_end, expected_datetime",
    [
        ("2025-02-19", False, datetime(2025, 2, 19, 0, 0, 0)),  # Start of the day
        (
            "2025-02-19",
            True,
            datetime(2025, 2, 19, 23, 59, 59, 999999),
        ),  # End of the day
        ("2023-01-01", False, datetime(2023, 1, 1, 0, 0, 0)),  # Start of the year
        (
            "2023-01-01",
            True,
            datetime(2023, 1, 1, 23, 59, 59, 999999),
        ),  # End of the year
        (
            "1999-12-31",
            False,
            datetime(1999, 12, 31, 0, 0, 0),
        ),  # Start of the millennium
        (
            "1999-12-31",
            True,
            datetime(1999, 12, 31, 23, 59, 59, 999999),
        ),  # End of the millennium
        (None, False, None),  # None should return None
        (None, True, None),  # None should return None (even with is_end=True)
    ],
)
def test_parse_date_range_1(date_str, is_end, expected_datetime):
    assert parse_date_range(date_str, is_end) == expected_datetime


@pytest.mark.parametrize(
    "date_str, date_format, is_end, expected_datetime",
    [
        (
            "19-02-2025",
            "%d-%m-%Y",
            False,
            datetime(2025, 2, 19, 0, 0, 0),
        ),  # Custom format (DD-MM-YYYY)
        (
            "19-02-2025",
            "%d-%m-%Y",
            True,
            datetime(2025, 2, 19, 23, 59, 59, 999999),
        ),  # Custom format end of day
        (
            "31/12/1999",
            "%d/%m/%Y",
            False,
            datetime(1999, 12, 31, 0, 0, 0),
        ),  # Slash-separated format start of day
        (
            "31/12/1999",
            "%d/%m/%Y",
            True,
            datetime(1999, 12, 31, 23, 59, 59, 999999),
        ),  # Slash-separated format end of day
    ],
)
def test_parse_date_range_with_different_formats(date_str, date_format, is_end, expected_datetime):
    assert parse_date_range(date_str, is_end, date_format) == expected_datetime


@pytest.mark.parametrize(
    "invalid_date, date_format",
    [
        ("2025-13-01", "%Y-%m-%d"),  # Invalid month
        ("2025-02-30", "%Y-%m-%d"),  # Invalid day
        ("02-31-2025", "%m-%d-%Y"),  # February has no 31st
        ("invalid-date", "%Y-%m-%d"),  # Completely invalid string
    ],
)
def test_parse_date_range_invalid_dates(invalid_date, date_format):
    with pytest.raises(ValueError):
        parse_date_range(invalid_date, date_format=date_format)
