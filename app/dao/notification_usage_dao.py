from datetime import datetime
from decimal import Decimal

from sqlalchemy import func

from app import db
from app.dao.date_util import get_financial_year
from app.models import (NotificationHistory,
                        Rate,
                        NOTIFICATION_STATUS_TYPES_BILLABLE,
                        KEY_TYPE_TEST,
                        SMS_TYPE,
                        EMAIL_TYPE)
from app.statsd_decorators import statsd
from app.utils import get_london_month_from_utc_column


@statsd(namespace="dao")
def get_yearly_billing_data(service_id, year):
    start_date, end_date = get_financial_year(year)
    rates = get_rates_for_year(start_date, end_date, SMS_TYPE)

    result = []
    for r, n in zip(rates, rates[1:]):
        result.append(
            sms_billing_data_query(str(r.rate), service_id, r.valid_from, n.valid_from))

    result.append(sms_billing_data_query(str(rates[-1].rate), service_id, rates[-1].valid_from, end_date))

    result.append(email_billing_data_query(service_id, start_date, end_date))

    return result


def billing_data_filter(notification_type, start_date, end_date, service_id):
    return [
        NotificationHistory.notification_type == notification_type,
        NotificationHistory.created_at >= start_date,
        NotificationHistory.created_at < end_date,
        NotificationHistory.service_id == service_id,
        NotificationHistory.status.in_(NOTIFICATION_STATUS_TYPES_BILLABLE),
        NotificationHistory.key_type != KEY_TYPE_TEST
    ]


def email_billing_data_query(service_id, start_date, end_date):
    result = db.session.query(
        func.count(NotificationHistory.id),
        NotificationHistory.notification_type,
        "0"
    ).filter(
        *billing_data_filter(EMAIL_TYPE, start_date, end_date, service_id)
    ).group_by(
        NotificationHistory.notification_type
    ).first()
    if not result:
        return 0, EMAIL_TYPE, Decimal("0")
    else:
        return result


def sms_billing_data_query(rate, service_id, start_date, end_date):
    result = db.session.query(
        func.sum(NotificationHistory.billable_units),
        NotificationHistory.notification_type,
        rate
    ).filter(
        *billing_data_filter(SMS_TYPE, start_date, end_date, service_id)
    ).group_by(
        NotificationHistory.notification_type
    ).first()
    if not result:
        return 0, SMS_TYPE, Decimal("0")
    else:
        return result


def get_rates_for_year(start_date, end_date, notification_type):
    return Rate.query.filter(Rate.valid_from >= start_date, Rate.valid_from < end_date,
                             Rate.notification_type == notification_type).order_by(Rate.valid_from).all()


def sms_billing_data_per_month_query(rate, service_id, start_date, end_date):
    month = get_london_month_from_utc_column(NotificationHistory.created_at)
    return db.session.query(
        month,
        func.sum(NotificationHistory.billable_units),
        NotificationHistory.notification_type,
        rate
    ).filter(
        *billing_data_filter(SMS_TYPE, start_date, end_date, service_id)
    ).group_by(
        NotificationHistory.notification_type, month
    ).order_by(
        month
    ).all()


def email_billing_data_per_month_query(rate, service_id, start_date, end_date):
    month = get_london_month_from_utc_column(NotificationHistory.created_at)
    return db.session.query(
        month,
        func.count(NotificationHistory.id),
        NotificationHistory.notification_type,
        rate
    ).filter(
        *billing_data_filter(EMAIL_TYPE, start_date, end_date, service_id)
    ).group_by(
        NotificationHistory.notification_type, month
    ).order_by(
        month
    ).all()


@statsd(namespace="dao")
def get_notification_billing_data_per_month(service_id, year):
    start_date, end_date = get_financial_year(year)
    rates = get_rates_for_year(start_date, end_date, SMS_TYPE)

    result = []
    for r, n in zip(rates, rates[1:]):
        result.extend(sms_billing_data_per_month_query(str(r.rate), service_id, r.valid_from, n.valid_from))
    result.extend(sms_billing_data_per_month_query(str(rates[-1].rate), service_id, rates[-1].valid_from, end_date))

    result.extend(email_billing_data_per_month_query("0", service_id, start_date, end_date))

    return [(datetime.strftime(x[0], "%B"), x[1:]) for x in result]
