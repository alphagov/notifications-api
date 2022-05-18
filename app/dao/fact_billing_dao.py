from datetime import date, datetime, timedelta

from flask import current_app
from notifications_utils.timezones import convert_utc_to_bst
from sqlalchemy import Date, Integer, and_, desc, func, union
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.sql.expression import case, literal

from app import db
from app.dao.date_util import (
    get_financial_year_dates,
    get_financial_year_for_datetime,
)
from app.dao.organisation_dao import dao_get_organisation_live_services
from app.models import (
    EMAIL_TYPE,
    INTERNATIONAL_POSTAGE_TYPES,
    KEY_TYPE_NORMAL,
    KEY_TYPE_TEAM,
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


def fetch_sms_free_allowance_remainder_until_date(end_date):
    # ASSUMPTION: AnnualBilling has been populated for year.
    billing_year = get_financial_year_for_datetime(end_date)
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
            FactBilling.bst_date < end_date,
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
    allowance_left_at_start_date_query = fetch_sms_free_allowance_remainder_until_date(start_date).subquery()

    sms_billable_units = func.sum(FactBilling.billable_units * FactBilling.rate_multiplier)

    # subtract sms_billable_units units accrued since report's start date to get up-to-date
    # allowance remainder
    sms_allowance_left = func.greatest(allowance_left_at_start_date_query.c.sms_remainder - sms_billable_units, 0)

    # billable units here are for period between start date and end date only, so to see
    # how many are chargeable, we need to see how much free allowance was used up in the
    # period up until report's start date and then do a subtraction
    chargeable_sms = func.greatest(sms_billable_units - allowance_left_at_start_date_query.c.sms_remainder, 0)
    sms_cost = chargeable_sms * FactBilling.rate

    query = db.session.query(
        Organisation.name.label('organisation_name'),
        Organisation.id.label('organisation_id'),
        Service.name.label("service_name"),
        Service.id.label("service_id"),
        allowance_left_at_start_date_query.c.free_sms_fragment_limit,
        FactBilling.rate.label('sms_rate'),
        sms_allowance_left.label("sms_remainder"),
        sms_billable_units.label('sms_billable_units'),
        chargeable_sms.label("chargeable_billable_sms"),
        sms_cost.label('sms_cost'),
    ).select_from(
        Service
    ).outerjoin(
        allowance_left_at_start_date_query, Service.id == allowance_left_at_start_date_query.c.service_id
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
        allowance_left_at_start_date_query.c.free_sms_fragment_limit,
        allowance_left_at_start_date_query.c.sms_remainder,
        FactBilling.rate,
    ).order_by(
        Organisation.name,
        Service.name
    )

    return query.all()


def fetch_letter_costs_and_totals_for_all_services(start_date, end_date):
    query = db.session.query(
        Organisation.name.label("organisation_name"),
        Organisation.id.label("organisation_id"),
        Service.name.label("service_name"),
        Service.id.label("service_id"),
        func.sum(FactBilling.notifications_sent).label("total_letters"),
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

    postage_order = case(
            (formatted_postage == "second", 1),
            (formatted_postage == "first", 2),
            (formatted_postage == "international", 3),
            else_=0  # assumes never get 0 as a result
    )

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
    """
    Returns a row for each distinct rate and notification_type from ft_billing
    over the specified financial year e.g.

        (
            rate=0.0165,
            notification_type=sms,
            notifications_sent=123,
            ...
        )

    The "query_service_<type>..." subqueries for each notification_type all
    return the same columns but differ internally e.g. SMS has to incorporate
    a rate multiplier. Each subquery returns the same set of columns, which we
    pick from here before the big union.
    """
    return db.session.query(
        union(*[
            db.session.query(
                query.c.notification_type.label("notification_type"),
                query.c.rate.label("rate"),

                func.sum(query.c.notifications_sent).label("notifications_sent"),
                func.sum(query.c.chargeable_units).label("chargeable_units"),
                func.sum(query.c.cost).label("cost"),
                func.sum(query.c.free_allowance_used).label("free_allowance_used"),
                func.sum(query.c.charged_units).label("charged_units"),
            ).group_by(
                query.c.rate,
                query.c.notification_type
            )
            for query in [
                query_service_sms_usage_for_year(service_id, year).subquery(),
                query_service_email_usage_for_year(service_id, year).subquery(),
                query_service_letter_usage_for_year(service_id, year).subquery(),
            ]
        ]).subquery()
    ).order_by(
        "notification_type",
        "rate",
    ).all()


def fetch_monthly_billing_for_year(service_id, year):
    """
    Returns a row for each distinct rate, notification_type, postage and month
    from ft_billing over the specified financial year e.g.

        (
            rate=0.0165,
            notification_type=sms,
            postage=none,
            month=2022-04-01 00:00:00,
            notifications_sent=123,
            ...
        )

    The "postage" field is "none" except for letters. Each subquery takes care
    of anything specific to the notification type e.g. rate multipliers for SMS.

    Since the data in ft_billing is only refreshed once a day for all services,
    we also update the table on-the-fly if we need accurate data for this year.
    """
    _, year_end = get_financial_year_dates(year)
    today = convert_utc_to_bst(datetime.utcnow()).date()

    # if year end date is less than today, we are calculating for data in the past and have no need for deltas.
    if year_end >= today:
        data = fetch_billing_data_for_day(process_day=today, service_id=service_id, check_permissions=True)
        for d in data:
            update_fact_billing(data=d, process_day=today)

    return db.session.query(
        union(*[
            db.session.query(
                query.c.rate.label("rate"),
                query.c.notification_type.label("notification_type"),
                query.c.postage.label("postage"),
                func.date_trunc('month', query.c.bst_date).cast(Date).label("month"),

                func.sum(query.c.notifications_sent).label("notifications_sent"),
                func.sum(query.c.chargeable_units).label("chargeable_units"),
                func.sum(query.c.cost).label("cost"),
                func.sum(query.c.free_allowance_used).label("free_allowance_used"),
                func.sum(query.c.charged_units).label("charged_units"),
            ).group_by(
                query.c.rate,
                query.c.notification_type,
                query.c.postage,
                'month',
            )
            for query in [
                query_service_sms_usage_for_year(service_id, year).subquery(),
                query_service_email_usage_for_year(service_id, year).subquery(),
                query_service_letter_usage_for_year(service_id, year).subquery(),
            ]
        ]).subquery()
    ).order_by(
        "month",
        "notification_type",
        "rate",
    ).all()


def query_service_email_usage_for_year(service_id, year):
    year_start, year_end = get_financial_year_dates(year)

    return db.session.query(
        FactBilling.bst_date,
        FactBilling.postage,  # should always be "none"
        FactBilling.notifications_sent,
        FactBilling.billable_units.label("chargeable_units"),
        FactBilling.rate,
        FactBilling.notification_type,
        literal(0).label("cost"),
        literal(0).label("free_allowance_used"),
        FactBilling.billable_units.label("charged_units"),
    ).filter(
        FactBilling.service_id == service_id,
        FactBilling.bst_date >= year_start,
        FactBilling.bst_date <= year_end,
        FactBilling.notification_type == EMAIL_TYPE
    )


def query_service_letter_usage_for_year(service_id, year):
    year_start, year_end = get_financial_year_dates(year)

    return db.session.query(
        FactBilling.bst_date,
        FactBilling.postage,
        FactBilling.notifications_sent,
        # We can't use billable_units here as it represents the
        # sheet count for letters, which is already accounted for
        # in the rate. We actually charge per letter, not sheet.
        FactBilling.notifications_sent.label("chargeable_units"),
        FactBilling.rate,
        FactBilling.notification_type,
        (FactBilling.notifications_sent * FactBilling.rate).label("cost"),
        literal(0).label("free_allowance_used"),
        FactBilling.notifications_sent.label("charged_units"),
    ).filter(
        FactBilling.service_id == service_id,
        FactBilling.bst_date >= year_start,
        FactBilling.bst_date <= year_end,
        FactBilling.notification_type == LETTER_TYPE
    )


def query_service_sms_usage_for_year(service_id, year):
    """
    Returns rows from the ft_billing table with some calculated values like cost,
    incorporating the SMS free allowance e.g.

        (
            bst_date=2022-04-27,
            notifications_sent=12,
            chargeable_units=12,
            rate=0.0165,
            [cost=0      <== covered by the free allowance],
            [cost=0.198  <== if free allowance exhausted],
            [cost=0.099  <== only some free allowance left],
            ...
        )

    In order to calculate how much free allowance is left, we need to work out
    how much was used for previous bst_dates - cumulative_chargeable_units -
    which we then subtract from the free allowance for the year.

    cumulative_chargeable_units is calculated using a "window" clause, which has
    access to all the rows identified by the query filter. Note that it's not
    affected by any GROUP BY clauses that happen in outer queries.

    https://www.postgresql.org/docs/current/tutorial-window.html

    ASSUMPTION: rates always change at midnight i.e. there can only be one rate
    on a given bst_date. This means we don't need to worry about how to assign
    free allowance if it happens to run out when a rate changes.
    """
    year_start, year_end = get_financial_year_dates(year)
    chargeable_units = FactBilling.billable_units * FactBilling.rate_multiplier

    # Subquery for the number of chargeable units in all rows preceding this one,
    # which might be none if this is the first row (hence the "coalesce"). For
    # some reason the end result is a decimal despite all the input columns being
    # integer - this seems to be a Sqlalchemy quirk (works in raw SQL).
    cumulative_chargeable_units = func.coalesce(
        func.sum(chargeable_units).over(
            # order is "ASC" by default
            order_by=[FactBilling.bst_date],
            # first row to previous row
            rows=(None, -1)
        ).cast(Integer),
        0
    )

    # Subquery for how much free allowance we have left before the current row,
    # so we can work out the cost for this row after taking it into account.
    cumulative_free_remainder = func.greatest(
        AnnualBilling.free_sms_fragment_limit - cumulative_chargeable_units,
        0
    )

    # Subquery for the number of chargeable_units that we will actually charge
    # for, after taking any remaining free allowance into account.
    charged_units = func.greatest(chargeable_units - cumulative_free_remainder, 0)

    free_allowance_used = func.least(cumulative_free_remainder, chargeable_units)

    return db.session.query(
        FactBilling.bst_date,
        FactBilling.postage,  # should always be "none"
        FactBilling.notifications_sent,
        chargeable_units.label("chargeable_units"),
        FactBilling.rate,
        FactBilling.notification_type,
        (charged_units * FactBilling.rate).label("cost"),
        free_allowance_used.label("free_allowance_used"),
        charged_units.label("charged_units"),
    ).join(
        AnnualBilling,
        AnnualBilling.service_id == service_id
    ).filter(
        FactBilling.service_id == service_id,
        FactBilling.bst_date >= year_start,
        FactBilling.bst_date <= year_end,
        FactBilling.notification_type == SMS_TYPE,
        AnnualBilling.financial_year_start == year,
    )


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
    start_date = get_london_midnight_in_utc(process_day)
    end_date = get_london_midnight_in_utc(process_day + timedelta(days=1))
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
            table.key_type.in_((KEY_TYPE_NORMAL, KEY_TYPE_TEAM)),
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
            table.key_type.in_((KEY_TYPE_NORMAL, KEY_TYPE_TEAM)),
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
            table.key_type.in_((KEY_TYPE_NORMAL, KEY_TYPE_TEAM)),
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
    allowance_left_at_start_date_query = fetch_sms_free_allowance_remainder_until_date(start_date).subquery()

    sms_billable_units = func.coalesce(func.sum(FactBilling.billable_units * FactBilling.rate_multiplier), 0)

    # subtract sms_billable_units units accrued since report's start date to get up-to-date
    # allowance remainder
    sms_allowance_left = func.greatest(allowance_left_at_start_date_query.c.sms_remainder - sms_billable_units, 0)

    # billable units here are for period between start date and end date only, so to see
    # how many are chargeable, we need to see how much free allowance was used up in the
    # period up until report's start date and then do a subtraction
    chargeable_sms = func.greatest(sms_billable_units - allowance_left_at_start_date_query.c.sms_remainder, 0)
    sms_cost = chargeable_sms * FactBilling.rate

    query = db.session.query(
        Service.name.label("service_name"),
        Service.id.label("service_id"),
        func.coalesce(allowance_left_at_start_date_query.c.free_sms_fragment_limit, 0).label('free_sms_fragment_limit'),
        func.coalesce(FactBilling.rate, 0).label('sms_rate'),
        func.coalesce(sms_allowance_left, 0).label("sms_remainder"),
        func.coalesce(sms_billable_units, 0).label('sms_billable_units'),
        func.coalesce(chargeable_sms, 0).label("chargeable_billable_sms"),
        func.coalesce(sms_cost, 0).label('sms_cost'),
        Service.active.label("active")
    ).select_from(
        Service
    ).outerjoin(
        allowance_left_at_start_date_query, Service.id == allowance_left_at_start_date_query.c.service_id
    ).outerjoin(
        FactBilling, and_(
            Service.id == FactBilling.service_id,
            FactBilling.bst_date >= start_date,
            FactBilling.bst_date < end_date,
            FactBilling.notification_type == SMS_TYPE,
        )
    ).filter(
        Service.organisation_id == organisation_id,
        Service.restricted.is_(False)
    ).group_by(
        Service.id,
        Service.name,
        allowance_left_at_start_date_query.c.free_sms_fragment_limit,
        allowance_left_at_start_date_query.c.sms_remainder,
        FactBilling.rate,
    ).order_by(
        Service.name
    )

    return query.all()


def fetch_usage_year_for_organisation(organisation_id, year):
    year_start, year_end = get_financial_year_dates(year)
    today = convert_utc_to_bst(datetime.utcnow()).date()
    services = dao_get_organisation_live_services(organisation_id)

    # if year end date is less than today, we are calculating for data in the past and have no need for deltas.
    if year_end >= today:
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
    sms_usages = fetch_sms_billing_for_organisation(organisation_id, year_start, year_end)
    letter_usages = fetch_letter_costs_for_organisation(organisation_id, year_start, year_end)
    email_usages = fetch_email_usage_for_organisation(organisation_id, year_start, year_end)
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


def fetch_daily_volumes_for_platform(start_date, end_date):
    # query to return the total notifications sent per day for each channel. NB start and end dates are inclusive

    daily_volume_stats = db.session.query(
        FactBilling.bst_date,
        func.sum(case(
            [
                (FactBilling.notification_type == SMS_TYPE, FactBilling.notifications_sent)
            ], else_=0
        )).label('sms_totals'),
        func.sum(case(
            [
                (FactBilling.notification_type == SMS_TYPE, FactBilling.billable_units)
            ], else_=0
        )).label('sms_fragment_totals'),
        func.sum(case(
            [
                (FactBilling.notification_type == SMS_TYPE, FactBilling.billable_units * FactBilling.rate_multiplier)
            ], else_=0
        )).label('sms_fragments_times_multiplier'),
        func.sum(case(
            [
                (FactBilling.notification_type == EMAIL_TYPE, FactBilling.notifications_sent)
            ], else_=0
        )).label('email_totals'),
        func.sum(case(
            [
                (FactBilling.notification_type == LETTER_TYPE, FactBilling.notifications_sent)
            ], else_=0
        )).label('letter_totals'),
        func.sum(case(
            [
                (FactBilling.notification_type == LETTER_TYPE, FactBilling.billable_units)
            ], else_=0
        )).label('letter_sheet_totals')
    ).filter(
        FactBilling.bst_date >= start_date,
        FactBilling.bst_date <= end_date
    ).group_by(
        FactBilling.bst_date,
        FactBilling.notification_type
    ).subquery()

    aggregated_totals = db.session.query(
        daily_volume_stats.c.bst_date.cast(db.Text).label('bst_date'),
        func.sum(daily_volume_stats.c.sms_totals).label('sms_totals'),
        func.sum(daily_volume_stats.c.sms_fragment_totals).label('sms_fragment_totals'),
        func.sum(
            daily_volume_stats.c.sms_fragments_times_multiplier).label('sms_chargeable_units'),
        func.sum(daily_volume_stats.c.email_totals).label('email_totals'),
        func.sum(daily_volume_stats.c.letter_totals).label('letter_totals'),
        func.sum(daily_volume_stats.c.letter_sheet_totals).label('letter_sheet_totals')
    ).group_by(
        daily_volume_stats.c.bst_date
    ).order_by(
        daily_volume_stats.c.bst_date
    ).all()

    return aggregated_totals


def fetch_daily_sms_provider_volumes_for_platform(start_date, end_date):
    # query to return the total notifications sent per day for each channel. NB start and end dates are inclusive

    daily_volume_stats = db.session.query(
        FactBilling.bst_date,
        FactBilling.provider,
        func.sum(FactBilling.notifications_sent).label('sms_totals'),
        func.sum(FactBilling.billable_units).label('sms_fragment_totals'),
        func.sum(FactBilling.billable_units * FactBilling.rate_multiplier).label('sms_chargeable_units'),
        func.sum(FactBilling.billable_units * FactBilling.rate_multiplier * FactBilling.rate).label('sms_cost'),
    ).filter(
        FactBilling.notification_type == SMS_TYPE,
        FactBilling.bst_date >= start_date,
        FactBilling.bst_date <= end_date,
    ).group_by(
        FactBilling.bst_date,
        FactBilling.provider,
    ).order_by(
        FactBilling.bst_date,
        FactBilling.provider,
    ).all()

    return daily_volume_stats


def fetch_volumes_by_service(start_date, end_date):
    # query to return the volume totals by service aggregated for the date range given
    # start and end dates are inclusive.
    year_end_date = int(end_date.strftime('%Y'))

    volume_stats = db.session.query(
        FactBilling.bst_date,
        FactBilling.service_id,
        func.sum(case([
            (FactBilling.notification_type == SMS_TYPE, FactBilling.notifications_sent)
        ], else_=0)).label('sms_totals'),
        func.sum(case([
            (FactBilling.notification_type == SMS_TYPE, FactBilling.billable_units * FactBilling.rate_multiplier)
        ], else_=0)).label('sms_fragments_times_multiplier'),
        func.sum(case([
            (FactBilling.notification_type == EMAIL_TYPE, FactBilling.notifications_sent)
        ], else_=0)).label('email_totals'),
        func.sum(case([
            (FactBilling.notification_type == LETTER_TYPE, FactBilling.notifications_sent)
        ], else_=0)).label('letter_totals'),
        func.sum(case([
            (FactBilling.notification_type == LETTER_TYPE, FactBilling.notifications_sent * FactBilling.rate)
        ], else_=0)).label("letter_cost"),
        func.sum(case(
            [
                (FactBilling.notification_type == LETTER_TYPE, FactBilling.billable_units)
            ], else_=0
        )).label('letter_sheet_totals')
    ).filter(
        FactBilling.bst_date >= start_date,
        FactBilling.bst_date <= end_date
    ).group_by(
        FactBilling.bst_date,
        FactBilling.service_id,
        FactBilling.notification_type
    ).subquery()

    annual_billing = db.session.query(
        func.max(AnnualBilling.financial_year_start).label('financial_year_start'),
        AnnualBilling.service_id,
        AnnualBilling.free_sms_fragment_limit
    ).filter(
        AnnualBilling.financial_year_start <= year_end_date
    ).group_by(
        AnnualBilling.service_id,
        AnnualBilling.free_sms_fragment_limit
    ).subquery()

    results = db.session.query(
        Service.name.label("service_name"),
        Service.id.label("service_id"),
        Service.organisation_id.label("organisation_id"),
        Organisation.name.label("organisation_name"),
        annual_billing.c.free_sms_fragment_limit.label("free_allowance"),
        func.coalesce(func.sum(volume_stats.c.sms_totals), 0).label("sms_notifications"),
        func.coalesce(func.sum(volume_stats.c.sms_fragments_times_multiplier), 0
                      ).label("sms_chargeable_units"),
        func.coalesce(func.sum(volume_stats.c.email_totals), 0).label("email_totals"),
        func.coalesce(func.sum(volume_stats.c.letter_totals), 0).label("letter_totals"),
        func.coalesce(func.sum(volume_stats.c.letter_cost), 0).label("letter_cost"),
        func.coalesce(func.sum(volume_stats.c.letter_sheet_totals), 0).label("letter_sheet_totals")
    ).select_from(
        Service
    ).outerjoin(
        Organisation, Service.organisation_id == Organisation.id
    ).join(
        annual_billing, Service.id == annual_billing.c.service_id
    ).outerjoin(  # include services without volume
        volume_stats, Service.id == volume_stats.c.service_id
    ).filter(
        Service.restricted.is_(False),
        Service.count_as_live.is_(True),
        Service.active.is_(True)
    ).group_by(
        Service.id,
        Service.name,
        Service.organisation_id,
        Organisation.name,
        annual_billing.c.free_sms_fragment_limit
    ).order_by(
        Organisation.name,
        Service.name,
    ).all()

    return results
