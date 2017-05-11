from datetime import datetime

from app.models import Rate
from app import db
from app.dao.dao_utils import transactional
from app.utils import get_london_midnight_in_utc


@transactional
def dao_create_rate(rate):
    db.session.add(rate)
    db.session.commit()


def get_current_rate():
    today = get_london_midnight_in_utc(datetime.utcnow())

    result = Rate.query.filter(Rate.valid_from <= today,
                             Rate.notification_type == 'sms').order_by(
                                 Rate.valid_from.desc()).first()

    if result:
        return result.rate
