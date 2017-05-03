from app.dao.date_util import get_financial_year, get_april_fools


def test_get_financial_year():
    start, end = get_financial_year(2000)
    assert str(start) == '2000-03-31 23:00:00'
    assert str(end) == '2001-03-31 22:59:59.999999'


def test_get_april_fools():
    april_fools = get_april_fools(2016)
    assert str(april_fools) == '2016-03-31 23:00:00'
    assert april_fools.tzinfo is None
