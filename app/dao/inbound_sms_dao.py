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


def dao_count_inbound_sms_for_service(service_id):
    return InboundSms.query.filter(
        InboundSms.service_id == service_id
    ).count()
