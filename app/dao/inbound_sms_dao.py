from datetime import (
    timedelta,
    datetime
)
from flask import current_app
from notifications_utils.statsd_decorators import statsd
from sqlalchemy import desc, and_
from sqlalchemy.orm import aliased

from app import db
from app.dao.dao_utils import transactional
from app.models import InboundSms


@transactional
def dao_create_inbound_sms(inbound_sms):
    db.session.add(inbound_sms)


def dao_get_inbound_sms_for_service(service_id, limit=None, user_number=None):
    q = InboundSms.query.filter(
        InboundSms.service_id == service_id
    ).order_by(
        InboundSms.created_at.desc()
    )

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


def dao_count_inbound_sms_for_service(service_id):
    return InboundSms.query.filter(
        InboundSms.service_id == service_id
    ).count()


@statsd(namespace="dao")
@transactional
def delete_inbound_sms_created_more_than_a_week_ago():
    seven_days_ago = datetime.utcnow() - timedelta(days=7)

    deleted = db.session.query(InboundSms).filter(
        InboundSms.created_at < seven_days_ago
    ).delete(synchronize_session='fetch')

    return deleted


def dao_get_inbound_sms_by_id(service_id, inbound_id):
    return InboundSms.query.filter_by(
        id=inbound_id,
        service_id=service_id
    ).one()


def dao_get_paginated_most_recent_inbound_sms_by_user_number_for_service(
    service_id,
    page
):
    """
    This query starts from inbound_sms and joins on to itself to find the most recent row for each user_number

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
            InboundSms.created_at < t2.created_at
        )
    ).filter(
        t2.id == None,  # noqa
        InboundSms.service_id == service_id
    ).order_by(
        InboundSms.created_at.desc()
    )

    return q.paginate(
        page=page,
        per_page=current_app.config['PAGE_SIZE']
    )
