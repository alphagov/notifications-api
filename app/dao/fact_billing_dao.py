from datetime import datetime, timedelta, time

from flask import current_app
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import func, case, desc, Date, Integer

from app import db
from app.dao.date_util import get_financial_year
from app.models import (
    FactBilling,
    Notification,
    Service,
    KEY_TYPE_TEST,
    LETTER_TYPE,
    SMS_TYPE,
    Rate,
    LetterRate,
    NOTIFICATION_STATUS_TYPES_BILLABLE,
    NotificationHistory,
    EMAIL_TYPE
)
from app.utils import convert_utc_to_bst, convert_bst_to_utc


def fetch_billing_totals_for_year(service_id, year):
    year_start_date, year_end_date = get_financial_year(year)
    """
      Billing for email: only record the total number of emails.
      Billing for letters: The billing units is used to fetch the correct rate for the sheet count of the letter.
      Total cost is notifications_sent * rate.
      Rate multiplier does not apply to email or letters.
    """
    email_and_letters = db.session.query(
        func.sum(FactBilling.notifications_sent).label("notifications_sent"),
        func.sum(FactBilling.notifications_sent).label("billable_units"),
        FactBilling.rate.label('rate'),
        FactBilling.notification_type.label('notification_type')
    ).filter(
        FactBilling.service_id == service_id,
        FactBilling.bst_date >= year_start_date,
        FactBilling.bst_date <= year_end_date,
        FactBilling.notification_type.in_([EMAIL_TYPE, LETTER_TYPE])
    ).group_by(
        FactBilling.rate,
        FactBilling.notification_type
    )
    """
    Billing for SMS using the billing_units * rate_multiplier. Billing unit of SMS is the fragment count of a message
    """
    sms = db.session.query(
        func.sum(FactBilling.notifications_sent).label("notifications_sent"),
        func.sum(FactBilling.billable_units * FactBilling.rate_multiplier).label("billable_units"),
        FactBilling.rate,
        FactBilling.notification_type
    ).filter(
        FactBilling.service_id == service_id,
        FactBilling.bst_date >= year_start_date,
        FactBilling.bst_date <= year_end_date,
        FactBilling.notification_type == SMS_TYPE
    ).group_by(
        FactBilling.rate,
        FactBilling.notification_type
    )

    yearly_data = email_and_letters.union_all(sms).order_by(
        'notification_type',
        'rate'
    ).all()

    return yearly_data


def fetch_monthly_billing_for_year(service_id, year):
    year_start_date, year_end_date = get_financial_year(year)
    utcnow = datetime.utcnow()
    today = convert_utc_to_bst(utcnow)
    # if year end date is less than today, we are calculating for data in the past and have no need for deltas.
    if year_end_date >= today:
        yesterday = today - timedelta(days=1)
        for day in [yesterday, today]:
            data = fetch_billing_data_for_day(process_day=day, service_id=service_id)
            for d in data:
                update_fact_billing(data=d, process_day=day)

    email_and_letters = db.session.query(
        func.date_trunc('month', FactBilling.bst_date).cast(Date).label("month"),
        func.sum(FactBilling.notifications_sent).label("notifications_sent"),
        func.sum(FactBilling.notifications_sent).label("billable_units"),
        FactBilling.rate.label('rate'),
        FactBilling.notification_type.label('notification_type')
    ).filter(
        FactBilling.service_id == service_id,
        FactBilling.bst_date >= year_start_date,
        FactBilling.bst_date <= year_end_date,
        FactBilling.notification_type.in_([EMAIL_TYPE, LETTER_TYPE])
    ).group_by(
        'month',
        FactBilling.rate,
        FactBilling.notification_type
    )

    sms = db.session.query(
        func.date_trunc('month', FactBilling.bst_date).cast(Date).label("month"),
        func.sum(FactBilling.notifications_sent).label("notifications_sent"),
        func.sum(FactBilling.billable_units * FactBilling.rate_multiplier).label("billable_units"),
        FactBilling.rate,
        FactBilling.notification_type
    ).filter(
        FactBilling.service_id == service_id,
        FactBilling.bst_date >= year_start_date,
        FactBilling.bst_date <= year_end_date,
        FactBilling.notification_type == SMS_TYPE
    ).group_by(
        'month',
        FactBilling.rate,
        FactBilling.notification_type
    )

    yearly_data = email_and_letters.union_all(sms).order_by(
        'month',
        'notification_type',
        'rate'
    ).all()

    return yearly_data


def delete_billing_data_for_service_for_day(process_day, service_id):
    """
    Delete all ft_billing data for a given service on a given bst_date

    Returns how many rows were deleted
    """
    return FactBilling.query.filter(
        FactBilling.bst_date == process_day,
        FactBilling.service_id == service_id
    ).delete()


def fetch_billing_data_for_day(process_day, service_id=None):
    start_date = convert_bst_to_utc(datetime.combine(process_day, time.min))
    end_date = convert_bst_to_utc(datetime.combine(process_day + timedelta(days=1), time.min))
    # use notification_history if process day is older than 7 days
    # this is useful if we need to rebuild the ft_billing table for a date older than 7 days ago.
    current_app.logger.info("Populate ft_billing for {} to {}".format(start_date, end_date))
    table = Notification
    if start_date < datetime.utcnow() - timedelta(days=7):
        table = NotificationHistory

    transit_data = db.session.query(
        table.template_id,
        table.service_id,
        table.notification_type,
        func.coalesce(table.sent_by,
                      case(
                          [
                              (table.notification_type == 'letter', 'dvla'),
                              (table.notification_type == 'sms', 'unknown'),
                              (table.notification_type == 'email', 'ses')
                          ]),
                      ).label('sent_by'),
        func.coalesce(table.rate_multiplier, 1).cast(Integer).label('rate_multiplier'),
        func.coalesce(table.international, False).label('international'),
        case(
            [
                (table.notification_type == 'letter', table.billable_units),
            ]
        ).label('letter_page_count'),
        func.sum(table.billable_units).label('billable_units'),
        func.count().label('notifications_sent'),
        Service.crown,
        func.coalesce(table.postage, 'none').label('postage')
    ).filter(
        table.status.in_(NOTIFICATION_STATUS_TYPES_BILLABLE),
        table.key_type != KEY_TYPE_TEST,
        table.created_at >= start_date,
        table.created_at < end_date
    ).group_by(
        table.template_id,
        table.service_id,
        table.notification_type,
        'sent_by',
        'letter_page_count',
        table.rate_multiplier,
        table.international,
        Service.crown,
        table.postage,
    ).join(
        Service
    )
    if service_id:
        transit_data = transit_data.filter(table.service_id == service_id)

    return transit_data.all()


def get_rates_for_billing():
    non_letter_rates = [(r.notification_type, r.valid_from, r.rate) for r in
                        Rate.query.order_by(desc(Rate.valid_from)).all()]
    letter_rates = [(r.start_date, r.crown, r.sheet_count, r.rate, r.post_class) for r in
                    LetterRate.query.order_by(desc(LetterRate.start_date)).all()]
    return non_letter_rates, letter_rates


def get_service_ids_that_need_billing_populated(start_date, end_date):
    return db.session.query(
        NotificationHistory.service_id
    ).filter(
        NotificationHistory.created_at >= start_date,
        NotificationHistory.created_at <= end_date,
        NotificationHistory.notification_type.in_([SMS_TYPE, EMAIL_TYPE, LETTER_TYPE]),
        NotificationHistory.billable_units != 0
    ).distinct().all()


def get_rate(
    non_letter_rates, letter_rates, notification_type, date, crown=None, letter_page_count=None, post_class='second'
):
    if notification_type == LETTER_TYPE:
        if letter_page_count == 0:
            return 0
        return next(
            r[3] for r in letter_rates if date >= r[0] and crown == r[1]
            and letter_page_count == r[2] and post_class == r[4]
        )
    elif notification_type == SMS_TYPE:
        return next(r[2] for r in non_letter_rates if notification_type == r[0] and date >= r[1])
    else:
        return 0


def update_fact_billing(data, process_day):
    non_letter_rates, letter_rates = get_rates_for_billing()
    rate = get_rate(non_letter_rates,
                    letter_rates,
                    data.notification_type,
                    process_day,
                    data.crown,
                    data.letter_page_count,
                    data.postage)
    billing_record = create_billing_record(data, rate, process_day)
    table = FactBilling.__table__
    '''
       This uses the Postgres upsert to avoid race conditions when two threads try to insert
       at the same row. The excluded object refers to values that we tried to insert but were
       rejected.
       http://docs.sqlalchemy.org/en/latest/dialects/postgresql.html#insert-on-conflict-upsert
    '''
    stmt = insert(table).values(
        bst_date=billing_record.bst_date,
        template_id=billing_record.template_id,
        service_id=billing_record.service_id,
        provider=billing_record.provider,
        rate_multiplier=billing_record.rate_multiplier,
        notification_type=billing_record.notification_type,
        international=billing_record.international,
        billable_units=billing_record.billable_units,
        notifications_sent=billing_record.notifications_sent,
        rate=billing_record.rate,
        postage=billing_record.postage,
    )

    stmt = stmt.on_conflict_do_update(
        constraint="ft_billing_pkey",
        set_={"notifications_sent": stmt.excluded.notifications_sent,
              "billable_units": stmt.excluded.billable_units,
              "updated_at": datetime.utcnow()
              }
    )
    db.session.connection().execute(stmt)
    db.session.commit()


def create_billing_record(data, rate, process_day):
    billing_record = FactBilling(
        bst_date=process_day.date(),
        template_id=data.template_id,
        service_id=data.service_id,
        notification_type=data.notification_type,
        provider=data.sent_by,
        rate_multiplier=data.rate_multiplier,
        international=data.international,
        billable_units=data.billable_units,
        notifications_sent=data.notifications_sent,
        rate=rate,
        postage=data.postage,
    )
    return billing_record
