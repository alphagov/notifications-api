from sqlalchemy import desc

from app import db
from app.models import Rates


def get_rate_for_type_and_date(notification_type, date_sent):
    return db.session.query(Rates).filter(Rates.notification_type == notification_type,
                                          Rates.valid_from <= date_sent
                                          ).order_by(Rates.valid_from.desc()
                                                     ).limit(1).first()
