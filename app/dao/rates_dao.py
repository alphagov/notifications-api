from sqlalchemy import desc

from app import db
from app.models import Rate


def get_rate_for_type_and_date(notification_type, date_sent):
    return db.session.query(Rate).filter(Rate.notification_type == notification_type,
                                         Rate.valid_from <= date_sent
                                         ).order_by(Rate.valid_from.desc()
                                                    ).limit(1).first()
