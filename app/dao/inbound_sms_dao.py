from flask import current_app
from notifications_utils.statsd_decorators import statsd
from sqlalchemy import desc, and_
from sqlalchemy.orm import aliased
from sqlalchemy.dialects.postgresql import insert

from app import db
from app.dao.dao_utils import transactional
from app.models import InboundSms, InboundSmsHistory, Service, ServiceDataRetention, SMS_TYPE
from app.utils import midnight_n_days_ago


@transactional
def dao_create_inbound_sms(inbound_sms):
    db.session.add(inbound_sms)


def dao_get_inbound_sms_for_service(service_id, user_number=None, *, limit_days=None, limit=None):
    q = InboundSms.query.filter(
        InboundSms.service_id == service_id
    ).order_by(
        InboundSms.created_at.desc()
    )
    if limit_days is not None:
        start_date = midnight_n_days_ago(limit_days)
        q = q.filter(InboundSms.created_at >= start_date)

    if user_number:
        q = q.filter(InboundSms.user_number == user_number)

    if limit:
        q = q.limit(limit)

    return q.all()


def dao_get_paginated_inbound_sms_for_service_for_public_api(
    service_id,
    older_than=None,
    page_size=None
):
    if page_size is None:
        page_size = current_app.config['PAGE_SIZE']

    filters = [InboundSms.service_id == service_id]

    if older_than:
        older_than_created_at = db.session.query(
            InboundSms.created_at).filter(InboundSms.id == older_than).as_scalar()
        filters.append(InboundSms.created_at < older_than_created_at)

    query = InboundSms.query.filter(*filters)

    return query.order_by(desc(InboundSms.created_at)).paginate(
        per_page=page_size
    ).items


def dao_count_inbound_sms_for_service(service_id, limit_days):
    return InboundSms.query.filter(
        InboundSms.service_id == service_id,
        InboundSms.created_at >= midnight_n_days_ago(limit_days)
    ).count()


def _delete_inbound_sms(datetime_to_delete_from, query_filter):
    query_limit = 10000

    subquery = db.session.query(
        InboundSms.id
    ).filter(
        InboundSms.created_at < datetime_to_delete_from,
        *query_filter
    ).limit(
        query_limit
    ).subquery()

    deleted = 0
    # set to nonzero just to enter the loop
    number_deleted = 1
    while number_deleted > 0:

        offset = 0
        inbound_sms_query = db.session.query(
            *[x.name for x in InboundSmsHistory.__table__.c]
        ).filter(InboundSms.id.in_(subquery))
        inbound_sms_count = inbound_sms_query.count()

        while offset < inbound_sms_count:
            statement = insert(InboundSmsHistory).from_select(
                InboundSmsHistory.__table__.c,
                inbound_sms_query.limit(query_limit).offset(offset)
            )

            statement = statement.on_conflict_do_update(
                constraint="inbound_sms_history_pkey",
                set_={
                    "created_at": statement.excluded.created_at,
                    "service_id": statement.excluded.service_id,
                    "notify_number": statement.excluded.notify_number,
                    "provider_date": statement.excluded.provider_date,
                    "provider_reference": statement.excluded.provider_reference,
                    "provider": statement.excluded.provider
                }
            )
            db.session.connection().execute(statement)

            offset += query_limit
        number_deleted = InboundSms.query.filter(InboundSms.id.in_(subquery)).delete(synchronize_session='fetch')
        deleted += number_deleted

    return deleted


@statsd(namespace="dao")
@transactional
def delete_inbound_sms_older_than_retention():
    current_app.logger.info('Deleting inbound sms for services with flexible data retention')

    flexible_data_retention = ServiceDataRetention.query.join(
        ServiceDataRetention.service,
        Service.inbound_number
    ).filter(
        ServiceDataRetention.notification_type == SMS_TYPE
    ).all()
    deleted = 0

    for f in flexible_data_retention:
        n_days_ago = midnight_n_days_ago(f.days_of_retention)

        current_app.logger.info("Deleting inbound sms for service id: {}".format(f.service_id))
        deleted += _delete_inbound_sms(n_days_ago, query_filter=[InboundSms.service_id == f.service_id])

    current_app.logger.info('Deleting inbound sms for services without flexible data retention')

    seven_days_ago = midnight_n_days_ago(7)

    deleted += _delete_inbound_sms(seven_days_ago, query_filter=[
        InboundSms.service_id.notin_(x.service_id for x in flexible_data_retention),
    ])
    current_app.logger.info('Deleted {} inbound sms'.format(deleted))
    return deleted


def insert_update_inbound_sms_history(date_to_delete_from, service_id, query_limit=10000):
    offset = 0
    inbound_sms_query = db.session.query(
        *[x.name for x in InboundSmsHistory.__table__.c]
    ).filter(
        InboundSms.service_id == service_id,
        InboundSms.created_at < date_to_delete_from,
    )
    inbound_sms_count = inbound_sms_query.count()

    while offset < inbound_sms_count:
        statement = insert(InboundSmsHistory).from_select(
            InboundSmsHistory.__table__.c,
            inbound_sms_query.limit(query_limit).offset(offset)
        )

        statement = statement.on_conflict_do_update(
            constraint="inbound_sms_history_pkey",
            set_={
                "created_at": statement.excluded.created_at,
                "service_id": statement.excluded.service_id,
                "notify_number": statement.excluded.notify_number,
                "provider_date": statement.excluded.provider_date,
                "provider_reference": statement.excluded.provider_reference,
                "provider": statement.excluded.provider
            }
        )
        db.session.connection().execute(statement)

        offset += query_limit


def dao_get_inbound_sms_by_id(service_id, inbound_id):
    return InboundSms.query.filter_by(
        id=inbound_id,
        service_id=service_id
    ).one()


def dao_get_paginated_most_recent_inbound_sms_by_user_number_for_service(
    service_id,
    page,
    limit_days
):
    """
    This query starts from inbound_sms and joins on to itself to find the most recent row for each user_number.

    Equivalent sql:

    SELECT t1.*
    FROM inbound_sms t1
    LEFT OUTER JOIN inbound_sms AS t2 ON (
        -- identifying
        t1.user_number = t2.user_number AND
        t1.service_id = t2.service_id AND
        -- ordering
        t1.created_at < t2.created_at
    )
    WHERE t2.id IS NULL AND t1.service_id = :service_id
    ORDER BY t1.created_at DESC;
    LIMIT 50 OFFSET :page
    """
    t2 = aliased(InboundSms)
    q = db.session.query(
        InboundSms
    ).outerjoin(
        t2,
        and_(
            InboundSms.user_number == t2.user_number,
            InboundSms.service_id == t2.service_id,
            InboundSms.created_at < t2.created_at,
        )
    ).filter(
        t2.id == None,  # noqa
        InboundSms.service_id == service_id,
        InboundSms.created_at >= midnight_n_days_ago(limit_days)
    ).order_by(
        InboundSms.created_at.desc()
    )

    return q.paginate(
        page=page,
        per_page=current_app.config['PAGE_SIZE']
    )
