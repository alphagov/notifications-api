from datetime import datetime, timedelta, time

from flask import current_app
from sqlalchemy import func, case, desc, extract

from app import db
from app.dao.date_util import get_financial_year
from app.models import (
    FactBilling,
    Notification,
    Service,
    NOTIFICATION_CREATED,
    NOTIFICATION_TECHNICAL_FAILURE,
    KEY_TYPE_TEST,
    LETTER_TYPE,
    SMS_TYPE,
    Rate,
    LetterRate
)
from app.utils import convert_utc_to_bst, convert_bst_to_utc


def fetch_annual_billing_for_year(service_id, year):
    year_start_date, year_end_date = get_financial_year(year)
    utcnow = datetime.utcnow()
    today = convert_utc_to_bst(utcnow).date()
    # if year end date is less than today, we are calculating for data in the past and have no need for deltas.
    if year_end_date.date() >= today:
        yesterday = today - timedelta(days=1)
        for day in [yesterday, today]:
            data = fetch_billing_data_for_day(process_day=day, service_id=service_id)
            for d in data:
                update_fact_billing(data=d, process_day=day)

    yearly_data = db.session.query(
        extract('month', FactBilling.bst_date).label("Month"),
        func.sum(FactBilling.notifications_sent).label("notifications_sent"),
        func.sum(FactBilling.billable_units).label("billable_units"),
        FactBilling.service_id,
        FactBilling.rate,
        FactBilling.rate_multiplier,
        FactBilling.international
    ).filter(
        FactBilling.service_id == service_id,
        FactBilling.bst_date >= year_start_date,
        FactBilling.bst_date <= year_end_date
    ).group_by(
        extract('month', FactBilling.bst_date),
        FactBilling.service_id,
        FactBilling.rate,
        FactBilling.rate_multiplier,
        FactBilling.international
    ).all()

    return yearly_data


def fetch_billing_data_for_day(process_day, service_id=None):
    start_date = convert_bst_to_utc(datetime.combine(process_day, time.min))
    end_date = convert_bst_to_utc(datetime.combine(process_day + timedelta(days=1), time.min))

    transit_data = db.session.query(
        Notification.template_id,
        Notification.service_id,
        Notification.notification_type,
        func.coalesce(Notification.sent_by,
                      case(
                          [
                              (Notification.notification_type == 'letter', 'dvla'),
                              (Notification.notification_type == 'sms', 'unknown'),
                              (Notification.notification_type == 'email', 'ses')
                          ]),
                      ).label('sent_by'),
        func.coalesce(Notification.rate_multiplier, 1).label('rate_multiplier'),
        func.coalesce(Notification.international, False).label('international'),
        func.sum(Notification.billable_units).label('billable_units'),
        func.count().label('notifications_sent'),
        Service.crown,
    ).filter(
        Notification.status != NOTIFICATION_CREATED,  # at created status, provider information is not available
        Notification.status != NOTIFICATION_TECHNICAL_FAILURE,
        Notification.key_type != KEY_TYPE_TEST,
        Notification.created_at >= start_date,
        Notification.created_at < end_date
    ).group_by(
        Notification.template_id,
        Notification.service_id,
        Notification.notification_type,
        'sent_by',
        Notification.rate_multiplier,
        Notification.international,
        Service.crown
    ).join(
        Service
    )
    if service_id:
        transit_data = transit_data.filter(Notification.service_id == service_id)
    return transit_data.all()


def get_rates_for_billing():
    non_letter_rates = [(r.notification_type, r.valid_from, r.rate) for r in
                        Rate.query.order_by(desc(Rate.valid_from)).all()]
    letter_rates = [(r.start_date, r.crown, r.sheet_count, r.rate) for r in
                    LetterRate.query.order_by(desc(LetterRate.start_date)).all()]
    return non_letter_rates, letter_rates


def get_rate(non_letter_rates, letter_rates, notification_type, date, crown=None, rate_multiplier=None):
    if notification_type == LETTER_TYPE:
        return next(r[3] for r in letter_rates if date > r[0] and crown == r[1] and rate_multiplier == r[2])
    elif notification_type == SMS_TYPE:
        return next(r[2] for r in non_letter_rates if notification_type == r[0] and date > r[1])
    else:
        return 0


def update_fact_billing(data, process_day):
    inserted_records = 0
    updated_records = 0
    non_letter_rates, letter_rates = get_rates_for_billing()

    update_count = FactBilling.query.filter(
        FactBilling.bst_date == datetime.date(process_day),
        FactBilling.template_id == data.template_id,
        FactBilling.service_id == data.service_id,
        FactBilling.provider == data.sent_by,  # This could be zero - this is a bug that needs to be fixed.
        FactBilling.rate_multiplier == data.rate_multiplier,
        FactBilling.notification_type == data.notification_type,
        FactBilling.international == data.international
    ).update(
        {"notifications_sent": data.notifications_sent,
         "billable_units": data.billable_units},
        synchronize_session=False)

    if update_count == 0:
        rate = get_rate(non_letter_rates,
                        letter_rates,
                        data.notification_type,
                        process_day,
                        data.crown,
                        data.rate_multiplier)
        billing_record = create_billing_record(data, rate, process_day)
        db.session.add(billing_record)
        inserted_records += 1
    updated_records += update_count
    db.session.commit()
    current_app.logger.info('ft_billing for {}: {} rows updated, {} rows inserted'
                            .format(process_day, updated_records, inserted_records))


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
        rate=rate
    )
    return billing_record
