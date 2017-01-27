from datetime import datetime
import pytest

from app.utils import (
    get_london_midnight_in_utc,
    get_midnight_for_day_before
)


@pytest.mark.parametrize('date, expected_date', [
    (datetime(2016, 1, 15, 0, 30), datetime(2016, 1, 15, 0, 0)),
    (datetime(2016, 6, 15, 0, 0), datetime(2016, 6, 14, 23, 0)),
    (datetime(2016, 9, 15, 11, 59), datetime(2016, 9, 14, 23, 0)),
])
def test_get_london_midnight_in_utc_returns_expected_date(date, expected_date):
    assert get_london_midnight_in_utc(date) == expected_date


@pytest.mark.parametrize('date, expected_date', [
    (datetime(2016, 1, 15, 0, 30), datetime(2016, 1, 14, 0, 0)),
    (datetime(2016, 7, 15, 0, 0), datetime(2016, 7, 13, 23, 0)),
    (datetime(2016, 8, 23, 11, 59), datetime(2016, 8, 21, 23, 0)),
])
def test_get_midnight_for_day_before_returns_expected_date(date, expected_date):
    assert get_midnight_for_day_before(date) == expected_date
