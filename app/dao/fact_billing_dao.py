from datetime import datetime, timedelta, time

from flask import current_app
from notifications_utils.timezones import convert_bst_to_utc, convert_utc_to_bst
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
    EMAIL_TYPE,
    NOTIFICATION_STATUS_TYPES_BILLABLE_FOR_LETTERS
)
from app.utils import get_london_midnight_in_utc


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
        FactBilling.notification_type.label('notification_type'),
        FactBilling.postage
    ).filter(
        FactBilling.service_id == service_id,
        FactBilling.bst_date >= year_start_date,
        FactBilling.bst_date <= year_end_date,
        FactBilling.notification_type.in_([EMAIL_TYPE, LETTER_TYPE])
    ).group_by(
        'month',
        FactBilling.rate,
        FactBilling.notification_type,
        FactBilling.postage
    )

    sms = db.session.query(
        func.date_trunc('month', FactBilling.bst_date).cast(Date).label("month"),
        func.sum(FactBilling.notifications_sent).label("notifications_sent"),
        func.sum(FactBilling.billable_units * FactBilling.rate_multiplier).label("billable_units"),
        FactBilling.rate,
        FactBilling.notification_type,
        FactBilling.postage
    ).filter(
        FactBilling.service_id == service_id,
        FactBilling.bst_date >= year_start_date,
        FactBilling.bst_date <= year_end_date,
        FactBilling.notification_type == SMS_TYPE
    ).group_by(
        'month',
        FactBilling.rate,
        FactBilling.notification_type,
        FactBilling.postage
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
    current_app.logger.info("Populate ft_billing for {} to {}".format(start_date, end_date))
    transit_data = []
    if not service_id:
        service_ids = [x.id for x in Service.query.all()]
    else:
        service_ids = [service_id]
    for id_of_service in service_ids:
        for notification_type in (SMS_TYPE, EMAIL_TYPE, LETTER_TYPE):
            results = _query_for_billing_data(
                table=Notification,
                notification_type=notification_type,
                start_date=start_date,
                end_date=end_date,
                service_id=id_of_service
            )
            # If data has been purged from Notification then use NotificationHistory
            if len(results) == 0:
                results = _query_for_billing_data(
                    table=NotificationHistory,
                    notification_type=notification_type,
                    start_date=start_date,
                    end_date=end_date,
                    service_id=id_of_service
                )

            transit_data = transit_data + results

    return transit_data


def _query_for_billing_data(table, notification_type, start_date, end_date, service_id):
    billable_type_list = {
        SMS_TYPE: NOTIFICATION_STATUS_TYPES_BILLABLE,
        EMAIL_TYPE: NOTIFICATION_STATUS_TYPES_BILLABLE,
        LETTER_TYPE: NOTIFICATION_STATUS_TYPES_BILLABLE_FOR_LETTERS
    }
    query = db.session.query(
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
        table.status.in_(billable_type_list[notification_type]),
        table.key_type != KEY_TYPE_TEST,
        table.created_at >= start_date,
        table.created_at < end_date,
        table.notification_type == notification_type,
        table.service_id == service_id
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
    return query.all()


def get_rates_for_billing():
    non_letter_rates = Rate.query.order_by(desc(Rate.valid_from)).all()
    letter_rates = LetterRate.query.order_by(desc(LetterRate.start_date)).all()
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
    start_of_day = get_london_midnight_in_utc(date)

    if notification_type == LETTER_TYPE:
        if letter_page_count == 0:
            return 0
        return next(
            r.rate
            for r in letter_rates if (
                start_of_day >= r.start_date and
                crown == r.crown and
                letter_page_count == r.sheet_count and
                post_class == r.post_class
            )
        )
    elif notification_type == SMS_TYPE:
        return next(
            r.rate
            for r in non_letter_rates if (
                notification_type == r.notification_type and
                start_of_day >= r.valid_from
            )
        )
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
        bst_date=process_day,
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
