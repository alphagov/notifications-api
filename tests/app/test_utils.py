from datetime import datetime
import pytest

from app.utils import (
    get_midnight_for_date,
    get_midnight_for_day_before
)


@pytest.mark.parametrize('date, expected_date', [
    (datetime(2016, 1, 15, 0, 30), datetime(2016, 1, 15, 0, 0)),
    (datetime(2016, 1, 15, 0, 0), datetime(2016, 1, 15, 0, 0)),
    (datetime(2016, 1, 15, 11, 59), datetime(2016, 1, 15, 0, 0)),
])
def test_get_midnight_for_today_returns_expected_date(date, expected_date):
    assert get_midnight_for_date(date) == expected_date


@pytest.mark.parametrize('date, expected_date', [
    (datetime(2016, 1, 15, 0, 30), datetime(2016, 1, 14, 0, 0)),
    (datetime(2016, 1, 15, 0, 0), datetime(2016, 1, 14, 0, 0)),
    (datetime(2016, 1, 15, 11, 59), datetime(2016, 1, 14, 0, 0)),
])
def test_get_midnight_for_day_before_returns_expected_date(date, expected_date):
    assert get_midnight_for_day_before(date) == expected_date
