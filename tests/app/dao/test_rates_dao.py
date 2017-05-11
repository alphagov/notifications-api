from datetime import datetime
import uuid

from freezegun import freeze_time

from app.dao.rates_dao import dao_create_rate, get_current_rate
from app.models import Rate
from tests.app.db import create_rate


def test_create_rates(notify_db, notify_db_session):
    data = {
        'id': uuid.uuid4(),
        'valid_from': datetime(2016, 3, 31, 23, 00),
        'rate': 0.015,
        'notification_type': 'sms'
    }

    rate = Rate(**data)
    dao_create_rate(rate)

    assert Rate.query.count() == 1
    assert Rate.query.first().rate == 0.015
    assert Rate.query.first().valid_from == datetime(2016, 3, 31, 23, 00)
    assert Rate.query.first().notification_type == 'sms'


@freeze_time("2017-05-1 12:30:00")
def test_get_current_rate(notify_db, notify_db_session):
    create_rate(datetime(2016, 3, 31, 23, 00), 0.015)
    create_rate(datetime(2017, 3, 31, 23, 00), 0.025)
    create_rate(datetime(2019, 3, 31, 23, 00), 0.035)

    rate = get_current_rate()
    assert rate == 0.025