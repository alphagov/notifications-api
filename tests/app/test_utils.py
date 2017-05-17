from datetime import datetime
import pytest

from app.utils import (
    get_london_midnight_in_utc,
    get_midnight_for_day_before,
    convert_utc_time_in_bst,
    convert_bst_to_utc)


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


@pytest.mark.parametrize('date, expected_date', [
    (datetime(2017, 3, 26, 23, 0), datetime(2017, 3, 27, 0, 0)),    # 2017 BST switchover
    (datetime(2017, 3, 20, 23, 0), datetime(2017, 3, 20, 23, 0)),
    (datetime(2017, 3, 28, 10, 0), datetime(2017, 3, 28, 11, 0)),
    (datetime(2017, 10, 28, 1, 0), datetime(2017, 10, 28, 2, 0)),
    (datetime(2017, 10, 29, 1, 0), datetime(2017, 10, 29, 1, 0)),
    (datetime(2017, 5, 12, 14), datetime(2017, 5, 12, 15, 0))
])
def test_get_utc_in_bst_returns_expected_date(date, expected_date):
    ret_date = convert_utc_time_in_bst(date)
    assert ret_date == expected_date


def test_convert_bst_to_utc():
    bst = "2017-05-12 13"
    bst_datetime = datetime.strptime(bst, "%Y-%m-%d %H")
    utc = convert_bst_to_utc(bst_datetime)
    assert utc == datetime(2017, 5, 12, 12, 0)
