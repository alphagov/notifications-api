from app import db
from app.dao.dao_utils import transactional


@transactional
def dao_create_inbound_sms(inbound_sms):
    db.session.add(inbound_sms)
