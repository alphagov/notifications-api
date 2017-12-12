from datetime import datetime, timedelta

from sqlalchemy import Float, Integer
from sqlalchemy import func, case, cast
from sqlalchemy import literal_column

from app import db
from app.dao.date_util import get_financial_year
from app.models import (
    NotificationHistory,
    Rate,
    NOTIFICATION_STATUS_TYPES_BILLABLE,
    KEY_TYPE_TEST,
    SMS_TYPE,
    EMAIL_TYPE,
    LETTER_TYPE,
    LetterRate,
    Service
)
from app.statsd_decorators import statsd
from app.utils import get_london_month_from_utc_column


@statsd(namespace="dao")
def get_billing_data_for_month(service_id, start_date, end_date, notification_type):
    results = []

    if notification_type == EMAIL_TYPE:
        return billing_data_per_month_query(0, service_id, start_date, end_date, EMAIL_TYPE)

    elif notification_type == SMS_TYPE:
        rates = get_rates_for_daterange(start_date, end_date, SMS_TYPE)

        if not rates:
            return []

        # so the start end date in the query are the valid from the rate, not the month
        # - this is going to take some thought
        for r, n in zip(rates, rates[1:]):
            results.extend(
                billing_data_per_month_query(
                    r.rate, service_id, max(r.valid_from, start_date),
                    min(n.valid_from, end_date), SMS_TYPE
                )
            )
        results.extend(
            billing_data_per_month_query(
                rates[-1].rate, service_id, max(rates[-1].valid_from, start_date),
                end_date, SMS_TYPE
            )
        )

    if notification_type == LETTER_TYPE:
        results.extend(billing_letter_data_per_month_query(
            service_id=service_id, start_date=start_date, end_date=end_date)
        )

    return results


@statsd(namespace="dao")
def get_monthly_billing_data(service_id, year):
    start_date, end_date = get_financial_year(year)
    rates = get_rates_for_daterange(start_date, end_date, SMS_TYPE)

    if not rates:
        return []

    result = []
    for r, n in zip(rates, rates[1:]):
        result.extend(billing_data_per_month_query(r.rate, service_id, r.valid_from, n.valid_from, SMS_TYPE))
    result.extend(billing_data_per_month_query(rates[-1].rate, service_id, rates[-1].valid_from, end_date, SMS_TYPE))

    return [(datetime.strftime(x[0], "%B"), x[1], x[2], x[3], x[4], x[5]) for x in result]


def billing_data_filter(notification_type, start_date, end_date, service_id):
    return [
        NotificationHistory.notification_type == notification_type,
        NotificationHistory.created_at.between(start_date, end_date),
        NotificationHistory.service_id == service_id,
        NotificationHistory.status.in_(NOTIFICATION_STATUS_TYPES_BILLABLE),
        NotificationHistory.key_type != KEY_TYPE_TEST
    ]


def get_rates_for_daterange(start_date, end_date, notification_type):
    rates = Rate.query.filter(Rate.notification_type == notification_type).order_by(Rate.valid_from).all()

    if not rates:
        return []

    results = []
    for current_rate, current_rate_expiry_date in zip(rates, rates[1:]):
        if is_between(current_rate.valid_from, start_date, end_date) or \
                is_between(current_rate_expiry_date.valid_from - timedelta(microseconds=1), start_date, end_date):
            results.append(current_rate)

    if is_between(rates[-1].valid_from, start_date, end_date):
        results.append(rates[-1])

    if not results:
        for x in reversed(rates):
            if start_date >= x.valid_from:
                results.append(x)
                break

    return results


def is_between(date, start_date, end_date):
    return start_date <= date <= end_date


@statsd(namespace="dao")
def billing_data_per_month_query(rate, service_id, start_date, end_date, notification_type):
    month = get_london_month_from_utc_column(NotificationHistory.created_at)
    if notification_type == SMS_TYPE:
        filter_subq = func.sum(NotificationHistory.billable_units).label('billing_units')
    elif notification_type == EMAIL_TYPE:
        filter_subq = func.count(NotificationHistory.billable_units).label('billing_units')

    results = db.session.query(
        month.label('month'),
        filter_subq,
        rate_multiplier().label('rate_multiplier'),
        NotificationHistory.international,
        NotificationHistory.notification_type,
        cast(rate, Float()).label('rate')
    ).filter(
        *billing_data_filter(notification_type, start_date, end_date, service_id)
    ).group_by(
        NotificationHistory.notification_type,
        month,
        NotificationHistory.rate_multiplier,
        NotificationHistory.international
    ).order_by(
        month,
        rate_multiplier()
    ).all()

    return results


def rate_multiplier():
    return cast(case([
        (NotificationHistory.rate_multiplier == None, literal_column("'1'")),  # noqa
        (NotificationHistory.rate_multiplier != None, NotificationHistory.rate_multiplier),  # noqa
    ]), Integer())


@statsd(namespace="dao")
def billing_letter_data_per_month_query(service_id, start_date, end_date):
    month = get_london_month_from_utc_column(NotificationHistory.created_at)
    crown = Service.query.get(service_id).crown
    results = db.session.query(
        month.label('month'),
        func.sum(NotificationHistory.billable_units).label('billing_units'),
        rate_multiplier().label('rate_multiplier'),
        NotificationHistory.international,
        NotificationHistory.notification_type,
        cast(LetterRate.rate, Float()).label('rate')
    ).filter(
        *billing_data_filter(LETTER_TYPE, start_date, end_date, service_id),
        LetterRate.sheet_count == NotificationHistory.billable_units,
        LetterRate.crown == crown,
        NotificationHistory.created_at.between(LetterRate.start_date, end_date),
        LetterRate.post_class == 'second'
    ).group_by(
        NotificationHistory.notification_type,
        month,
        NotificationHistory.rate_multiplier,
        NotificationHistory.international,
        LetterRate.rate
    ).order_by(
        month,
        rate_multiplier()
    ).all()

    return results
