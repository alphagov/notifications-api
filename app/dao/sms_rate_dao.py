from datetime import datetime

from sqlalchemy import desc

from app.models import Rate


def dao_get_current_sms_rate():
    return Rate.query.filter(Rate.valid_from <= datetime.utcnow()).order_by(desc(Rate.valid_from)).first()
