from datetime import datetime
from decimal import Decimal

from freezegun import freeze_time

from app.dao.date_util import get_month_start_and_end_date_in_utc
from app.dao.fact_billing_dao import fetch_annual_billing_by_month, need_deltas
from tests.app.db import create_ft_billing, create_service, create_template, create_notification


def test_fetch_annual_billing_by_month(notify_db_session):
    service = create_service()
    template = create_template(service=service, template_type="email")
    for i in range(1, 32):
        record = create_ft_billing(bst_date='2018-01-{}'.format(i),
                                   service=service,
                                   template=template,
                                   notification_type='email')

    results, month = fetch_annual_billing_by_month(service_id=record.service_id,
                                                   billing_month=datetime(2018, 1, 1),
                                                   notification_type='email')

    assert len(results) == 1
    assert results[0] == (31, Decimal('31'), service.id, 'email', Decimal('0'), Decimal('1'), False)
    assert month == datetime(2018, 1, 1)


@freeze_time("2018-01-21 13:00:00")
def test_need_deltas(notify_db_session):
    service = create_service()
    template = create_template(service=service, template_type="email")
    for i in range(1, 21):
        record = create_ft_billing(bst_date='2018-01-{}'.format(i),
                                   service=service,
                                   template=template,
                                   notification_type='email')
    start_date, end_date = get_month_start_and_end_date_in_utc(datetime.utcnow())

    result = need_deltas(start_date=start_date, end_date=end_date,
                         service_id=service.id, notification_type='email')
    assert result
