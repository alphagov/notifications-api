from datetime import date, datetime, time, timedelta

from flask import current_app
from notifications_utils.timezones import convert_bst_to_utc, convert_utc_to_bst
from sqlalchemy import Date, Integer, and_, desc, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.sql.expression import case, literal

from app import db
from app.dao.date_util import (
    get_financial_year,
    get_financial_year_for_datetime,
)
from app.dao.organisation_dao import dao_get_organisation_live_services
from app.models import (
    EMAIL_TYPE,
    INTERNATIONAL_POSTAGE_TYPES,
    KEY_TYPE_TEST,
    LETTER_TYPE,
    NOTIFICATION_STATUS_TYPES_BILLABLE_FOR_LETTERS,
    NOTIFICATION_STATUS_TYPES_BILLABLE_SMS,
    NOTIFICATION_STATUS_TYPES_SENT_EMAILS,
    SMS_TYPE,
    AnnualBilling,
    FactBilling,
    LetterRate,
    NotificationHistory,
    Organisation,
    Rate,
    Service,
)
from app.utils import get_london_midnight_in_utc, get_notification_table_to_use


def fetch_sms_free_allowance_remainder(start_date):
    # ASSUMPTION: AnnualBilling has been populated for year.
    billing_year = get_financial_year_for_datetime(start_date)
    start_of_year = date(billing_year, 4, 1)

    billable_units = func.coalesce(func.sum(FactBilling.billable_units * FactBilling.rate_multiplier), 0)

    query = db.session.query(
        AnnualBilling.service_id.label("service_id"),
        AnnualBilling.free_sms_fragment_limit,
        billable_units.label('billable_units'),
        func.greatest((AnnualBilling.free_sms_fragment_limit - billable_units).cast(Integer), 0).label('sms_remainder')
    ).outerjoin(
        # if there are no ft_billing rows for a service we still want to return the annual billing so we can use the
        # free_sms_fragment_limit)
        FactBilling, and_(
            AnnualBilling.service_id == FactBilling.service_id,
            FactBilling.bst_date >= start_of_year,
            FactBilling.bst_date < start_date,
            FactBilling.notification_type == SMS_TYPE,
        )
    ).filter(
        AnnualBilling.financial_year_start == billing_year,
    ).group_by(
        AnnualBilling.service_id,
        AnnualBilling.free_sms_fragment_limit,
    )
    return query


def fetch_sms_billing_for_all_services(start_date, end_date):

    # ASSUMPTION: AnnualBilling has been populated for year.
    free_allowance_remainder = fetch_sms_free_allowance_remainder(start_date).subquery()

    sms_billable_units = func.sum(FactBilling.billable_units * FactBilling.rate_multiplier)
    sms_remainder = func.coalesce(
        free_allowance_remainder.c.sms_remainder,
        free_allowance_remainder.c.free_sms_fragment_limit
    )
    chargeable_sms = func.greatest(sms_billable_units - sms_remainder, 0)
    sms_cost = chargeable_sms * FactBilling.rate

    query = db.session.query(
        Organisation.name.label('organisation_name'),
        Organisation.id.label('organisation_id'),
        Service.name.label("service_name"),
        Service.id.label("service_id"),
        free_allowance_remainder.c.free_sms_fragment_limit,
        FactBilling.rate.label('sms_rate'),
        sms_remainder.label("sms_remainder"),
        sms_billable_units.label('sms_billable_units'),
        chargeable_sms.label("chargeable_billable_sms"),
        sms_cost.label('sms_cost'),
    ).select_from(
        Service
    ).outerjoin(
        free_allowance_remainder, Service.id == free_allowance_remainder.c.service_id
    ).outerjoin(
        Service.organisation
    ).join(
        FactBilling, FactBilling.service_id == Service.id,
    ).filter(
        FactBilling.bst_date >= start_date,
        FactBilling.bst_date <= end_date,
        FactBilling.notification_type == SMS_TYPE,
    ).group_by(
        Organisation.name,
        Organisation.id,
        Service.id,
        Service.name,
        free_allowance_remainder.c.free_sms_fragment_limit,
        free_allowance_remainder.c.sms_remainder,
        FactBilling.rate,
    ).order_by(
        Organisation.name,
        Service.name
    )

    return query.all()


def fetch_letter_costs_for_all_services(start_date, end_date):
    query = db.session.query(
        Organisation.name.label("organisation_name"),
        Organisation.id.label("organisation_id"),
        Service.name.label("service_name"),
        Service.id.label("service_id"),
        func.sum(FactBilling.notifications_sent * FactBilling.rate).label("letter_cost")
    ).select_from(
        Service
    ).outerjoin(
        Service.organisation
    ).join(
        FactBilling, FactBilling.service_id == Service.id,
    ).filter(
        FactBilling.service_id == Service.id,
        FactBilling.bst_date >= start_date,
        FactBilling.bst_date <= end_date,
        FactBilling.notification_type == LETTER_TYPE,
    ).group_by(
        Organisation.name,
        Organisation.id,
        Service.id,
        Service.name,
    ).order_by(
        Organisation.name,
        Service.name
    )

    return query.all()


def fetch_letter_line_items_for_all_services(start_date, end_date):
    formatted_postage = case(
        [(FactBilling.postage.in_(INTERNATIONAL_POSTAGE_TYPES), "international")], else_=FactBilling.postage
    ).label("postage")

    postage_order = case(((formatted_postage == "second", 1),
                          (formatted_postage == "first", 2),
                          (formatted_postage == "international", 3)))

    query = db.session.query(
        Organisation.name.label("organisation_name"),
        Organisation.id.label("organisation_id"),
        Service.name.label("service_name"),
        Service.id.label("service_id"),
        FactBilling.rate.label("letter_rate"),
        formatted_postage,
        func.sum(FactBilling.notifications_sent).label("letters_sent"),
    ).select_from(
        Service
    ).outerjoin(
        Service.organisation
    ).join(
        FactBilling, FactBilling.service_id == Service.id,
    ).filter(
        FactBilling.bst_date >= start_date,
        FactBilling.bst_date <= end_date,
        FactBilling.notification_type == LETTER_TYPE,
    ).group_by(
        Organisation.name,
        Organisation.id,
        Service.id,
        Service.name,
        FactBilling.rate,
        formatted_postage
    ).order_by(
        Organisation.name,
        Service.name,
        postage_order,
        FactBilling.rate,
    )
    return query.all()


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
    year_start_datetime, year_end_datetime = get_financial_year(year)

    year_start_date = convert_utc_to_bst(year_start_datetime).date()
    year_end_date = convert_utc_to_bst(year_end_datetime).date()

    today = convert_utc_to_bst(datetime.utcnow()).date()
    # if year end date is less than today, we are calculating for data in the past and have no need for deltas.
    if year_end_date >= today:
        data = fetch_billing_data_for_day(process_day=today, service_id=service_id, check_permissions=True)
        for d in data:
            update_fact_billing(data=d, process_day=today)

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


def fetch_billing_data_for_day(process_day, service_id=None, check_permissions=False):
    start_date = convert_bst_to_utc(datetime.combine(process_day, time.min))
    end_date = convert_bst_to_utc(datetime.combine(process_day + timedelta(days=1), time.min))
    current_app.logger.info("Populate ft_billing for {} to {}".format(start_date, end_date))
    transit_data = []
    if not service_id:
        services = Service.query.all()
    else:
        services = [Service.query.get(service_id)]

    for service in services:
        for notification_type in (SMS_TYPE, EMAIL_TYPE, LETTER_TYPE):
            if (not check_permissions) or service.has_permission(notification_type):
                table = get_notification_table_to_use(service, notification_type, process_day,
                                                      has_delete_task_run=False)
                results = _query_for_billing_data(
                    table=table,
                    notification_type=notification_type,
                    start_date=start_date,
                    end_date=end_date,
                    service=service
                )
                transit_data += results

    return transit_data


def _query_for_billing_data(table, notification_type, start_date, end_date, service):
    def _email_query():
        return db.session.query(
            table.template_id,
            literal(service.crown).label('crown'),
            literal(service.id).label('service_id'),
            literal(notification_type).label('notification_type'),
            literal('ses').label('sent_by'),
            literal(0).label('rate_multiplier'),
            literal(False).label('international'),
            literal(None).label('letter_page_count'),
            literal('none').label('postage'),
            literal(0).label('billable_units'),
            func.count().label('notifications_sent'),
        ).filter(
            table.status.in_(NOTIFICATION_STATUS_TYPES_SENT_EMAILS),
            table.key_type != KEY_TYPE_TEST,
            table.created_at >= start_date,
            table.created_at < end_date,
            table.notification_type == notification_type,
            table.service_id == service.id
        ).group_by(
            table.template_id,
        )

    def _sms_query():
        sent_by = func.coalesce(table.sent_by, 'unknown')
        rate_multiplier = func.coalesce(table.rate_multiplier, 1).cast(Integer)
        international = func.coalesce(table.international, False)
        return db.session.query(
            table.template_id,
            literal(service.crown).label('crown'),
            literal(service.id).label('service_id'),
            literal(notification_type).label('notification_type'),
            sent_by.label('sent_by'),
            rate_multiplier.label('rate_multiplier'),
            international.label('international'),
            literal(None).label('letter_page_count'),
            literal('none').label('postage'),
            func.sum(table.billable_units).label('billable_units'),
            func.count().label('notifications_sent'),
        ).filter(
            table.status.in_(NOTIFICATION_STATUS_TYPES_BILLABLE_SMS),
            table.key_type != KEY_TYPE_TEST,
            table.created_at >= start_date,
            table.created_at < end_date,
            table.notification_type == notification_type,
            table.service_id == service.id
        ).group_by(
            table.template_id,
            sent_by,
            rate_multiplier,
            international,
        )

    def _letter_query():
        rate_multiplier = func.coalesce(table.rate_multiplier, 1).cast(Integer)
        postage = func.coalesce(table.postage, 'none')
        return db.session.query(
            table.template_id,
            literal(service.crown).label('crown'),
            literal(service.id).label('service_id'),
            literal(notification_type).label('notification_type'),
            literal('dvla').label('sent_by'),
            rate_multiplier.label('rate_multiplier'),
            table.international,
            table.billable_units.label('letter_page_count'),
            postage.label('postage'),
            func.sum(table.billable_units).label('billable_units'),
            func.count().label('notifications_sent'),
        ).filter(
            table.status.in_(NOTIFICATION_STATUS_TYPES_BILLABLE_FOR_LETTERS),
            table.key_type != KEY_TYPE_TEST,
            table.created_at >= start_date,
            table.created_at < end_date,
            table.notification_type == notification_type,
            table.service_id == service.id
        ).group_by(
            table.template_id,
            rate_multiplier,
            table.billable_units,
            postage,
            table.international
        )

    query_funcs = {
        SMS_TYPE: _sms_query,
        EMAIL_TYPE: _email_query,
        LETTER_TYPE: _letter_query
    }

    query = query_funcs[notification_type]()
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
        # if crown is not set default to true, this is okay because the rates are the same for both crown and non-crown.
        crown = crown or True
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


def fetch_letter_costs_for_organisation(organisation_id, start_date, end_date):
    query = db.session.query(
        Service.name.label("service_name"),
        Service.id.label("service_id"),
        func.sum(FactBilling.notifications_sent * FactBilling.rate).label("letter_cost")
    ).select_from(
        Service
    ).join(
        FactBilling, FactBilling.service_id == Service.id,
    ).filter(
        FactBilling.bst_date >= start_date,
        FactBilling.bst_date <= end_date,
        FactBilling.notification_type == LETTER_TYPE,
        Service.organisation_id == organisation_id,
        Service.restricted.is_(False)
    ).group_by(
        Service.id,
        Service.name,
    ).order_by(
        Service.name
    )

    return query.all()


def fetch_email_usage_for_organisation(organisation_id, start_date, end_date):
    query = db.session.query(
        Service.name.label("service_name"),
        Service.id.label("service_id"),
        func.sum(FactBilling.notifications_sent).label("emails_sent")
    ).select_from(
        Service
    ).join(
        FactBilling, FactBilling.service_id == Service.id,
    ).filter(
        FactBilling.bst_date >= start_date,
        FactBilling.bst_date <= end_date,
        FactBilling.notification_type == EMAIL_TYPE,
        Service.organisation_id == organisation_id,
        Service.restricted.is_(False)
    ).group_by(
        Service.id,
        Service.name,
    ).order_by(
        Service.name
    )
    return query.all()


def fetch_sms_billing_for_organisation(organisation_id, start_date, end_date):
    # ASSUMPTION: AnnualBilling has been populated for year.
    free_allowance_remainder = fetch_sms_free_allowance_remainder(start_date).subquery()

    sms_billable_units = func.sum(FactBilling.billable_units * FactBilling.rate_multiplier)
    sms_remainder = func.coalesce(
        free_allowance_remainder.c.sms_remainder,
        free_allowance_remainder.c.free_sms_fragment_limit
    )
    chargeable_sms = func.greatest(sms_billable_units - sms_remainder, 0)
    sms_cost = chargeable_sms * FactBilling.rate

    query = db.session.query(
        Service.name.label("service_name"),
        Service.id.label("service_id"),
        free_allowance_remainder.c.free_sms_fragment_limit,
        FactBilling.rate.label('sms_rate'),
        sms_remainder.label("sms_remainder"),
        sms_billable_units.label('sms_billable_units'),
        chargeable_sms.label("chargeable_billable_sms"),
        sms_cost.label('sms_cost'),
        Service.active.label("active")
    ).select_from(
        Service
    ).outerjoin(
        free_allowance_remainder, Service.id == free_allowance_remainder.c.service_id
    ).join(
        FactBilling, FactBilling.service_id == Service.id,
    ).filter(
        FactBilling.bst_date >= start_date,
        FactBilling.bst_date <= end_date,
        FactBilling.notification_type == SMS_TYPE,
        Service.organisation_id == organisation_id,
        Service.restricted.is_(False)
    ).group_by(
        Service.id,
        Service.name,
        free_allowance_remainder.c.free_sms_fragment_limit,
        free_allowance_remainder.c.sms_remainder,
        FactBilling.rate,
    ).order_by(
        Service.name
    )

    return query.all()


def fetch_usage_year_for_organisation(organisation_id, year):
    year_start_datetime, year_end_datetime = get_financial_year(year)

    year_start_date = convert_utc_to_bst(year_start_datetime).date()
    year_end_date = convert_utc_to_bst(year_end_datetime).date()

    today = convert_utc_to_bst(datetime.utcnow()).date()
    services = dao_get_organisation_live_services(organisation_id)
    # if year end date is less than today, we are calculating for data in the past and have no need for deltas.
    if year_end_date >= today:
        for service in services:
            data = fetch_billing_data_for_day(process_day=today, service_id=service.id)
            for d in data:
                update_fact_billing(data=d, process_day=today)
    service_with_usage = {}
    # initialise results
    for service in services:
        service_with_usage[str(service.id)] = {
            'service_id': service.id,
            'service_name': service.name,
            'free_sms_limit': 0,
            'sms_remainder': 0,
            'sms_billable_units': 0,
            'chargeable_billable_sms': 0,
            'sms_cost': 0.0,
            'letter_cost': 0.0,
            'emails_sent': 0,
            'active': service.active
        }
    sms_usages = fetch_sms_billing_for_organisation(organisation_id, year_start_date, year_end_date)
    letter_usages = fetch_letter_costs_for_organisation(organisation_id, year_start_date, year_end_date)
    email_usages = fetch_email_usage_for_organisation(organisation_id, year_start_date, year_end_date)
    for usage in sms_usages:
        service_with_usage[str(usage.service_id)] = {
            'service_id': usage.service_id,
            'service_name': usage.service_name,
            'free_sms_limit': usage.free_sms_fragment_limit,
            'sms_remainder': usage.sms_remainder,
            'sms_billable_units': usage.sms_billable_units,
            'chargeable_billable_sms': usage.chargeable_billable_sms,
            'sms_cost': float(usage.sms_cost),
            'letter_cost': 0.0,
            'emails_sent': 0,
            'active': usage.active
        }
    for letter_usage in letter_usages:
        service_with_usage[str(letter_usage.service_id)]['letter_cost'] = float(letter_usage.letter_cost)
    for email_usage in email_usages:
        service_with_usage[str(email_usage.service_id)]['emails_sent'] = email_usage.emails_sent

    return service_with_usage


def fetch_billing_details_for_all_services():
    billing_details = db.session.query(
        Service.id.label('service_id'),
        func.coalesce(Service.purchase_order_number, Organisation.purchase_order_number).label('purchase_order_number'),
        func.coalesce(Service.billing_contact_names, Organisation.billing_contact_names).label('billing_contact_names'),
        func.coalesce(
            Service.billing_contact_email_addresses,
            Organisation.billing_contact_email_addresses
        ).label('billing_contact_email_addresses'),
        func.coalesce(Service.billing_reference, Organisation.billing_reference).label('billing_reference'),
    ).outerjoin(
        Service.organisation
    ).all()

    return billing_details
