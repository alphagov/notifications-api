from datetime import datetime, timedelta

import pytz


def get_financial_year(year):
    return get_april_fools(year), get_april_fools(year + 1) - timedelta(microseconds=1)


def get_april_fools(year):
    """
     This function converts the start of the financial year April 1, 00:00 as BST (British Standard Time) to UTC,
     the tzinfo is lastly removed from the datetime becasue the database stores the timestamps without timezone.
     :param year: the year to calculate the April 1, 00:00 BST for
     :return: the datetime of April 1 for the given year, for example 2016 = 2016-03-31 23:00:00
    """
    return pytz.timezone('Europe/London').localize(datetime(year, 4, 1, 0, 0, 0)).astimezone(pytz.UTC).replace(
        tzinfo=None)


def get_month_start_end_date(month_year):
    """
     This function return the start and date of the month_year as UTC,
     :param month_year: the datetime to calculate the start and end date for that month
     :return: start_date, end_date, month
    """
    import calendar
    _, num_days = calendar.monthrange(month_year.year, month_year.month)
    first_day = datetime(month_year.year, month_year.month, 1, 0, 0, 0)
    last_day = datetime(month_year.year, month_year.month, num_days, 23, 59, 59, 99999)
    return first_day, last_day
