from datetime import (
    timedelta,
    datetime
)


from app import db
from app.dao.dao_utils import transactional
from app.models import InboundSms
from app.statsd_decorators import statsd


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
